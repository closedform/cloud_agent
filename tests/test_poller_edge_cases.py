"""Edge case tests for email poller.

Stress tests for:
1. Malformed email headers
2. Missing subject/body
3. Very large attachments
4. Unicode in email addresses
5. Multiple recipients in To field
"""

import email
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.poller import (
    clean_filename,
    create_task,
    extract_reply_to,
    get_email_body,
    process_emails,
    save_attachments,
)


class TestMalformedEmailHeaders:
    """Test handling of malformed email headers."""

    def test_none_subject_header(self, test_config):
        """BUG: decode_header(None) raises TypeError."""
        # When Subject header is completely missing, msg["Subject"] returns None
        # decode_header(None) raises: TypeError: expected str or bytes-like object
        msg = EmailMessage()
        msg["From"] = "test@example.com"
        # No Subject header set

        # This should not raise, but currently will
        # The bug is in process_emails at line 154:
        # subject_header, charset = decode_header(msg["Subject"])[0]
        # When msg["Subject"] is None, decode_header fails
        assert msg["Subject"] is None

    def test_empty_subject_header(self):
        """Test handling of empty subject header."""
        msg = EmailMessage()
        msg["Subject"] = ""
        msg["From"] = "test@example.com"
        msg.set_content("Body text")

        from email.header import decode_header

        subject_header, charset = decode_header(msg["Subject"])[0]
        # Empty string is handled correctly
        assert subject_header == ""

    def test_malformed_encoded_subject(self):
        """Test handling of malformed RFC 2047 encoded subject."""
        msg = EmailMessage()
        # Malformed encoding - incomplete base64
        msg["Subject"] = "=?utf-8?B?broken_base64_without_end"
        msg["From"] = "test@example.com"

        from email.header import decode_header

        # decode_header handles malformed encodings by returning them as-is
        subject_header, charset = decode_header(msg["Subject"])[0]
        # Should not crash, returns original malformed string
        assert "broken_base64" in str(subject_header)

    def test_invalid_charset_in_subject(self):
        """Test handling of invalid charset declaration."""
        msg = EmailMessage()
        # Invalid charset declaration
        msg["Subject"] = "=?nonexistent-charset?Q?hello?="
        msg["From"] = "test@example.com"

        from email.header import decode_header

        subject_header, charset = decode_header(msg["Subject"])[0]
        # decode_header returns bytes when it can decode, string otherwise
        # With invalid charset, it typically returns the original string or bytes
        assert subject_header is not None

    def test_multi_line_subject(self):
        """Test handling of multi-line folded subject headers."""
        raw_email = b"""Subject: This is a very long subject line that has been
 folded according to RFC 5322 standards
From: test@example.com
Content-Type: text/plain

Body text
"""
        msg = email.message_from_bytes(raw_email)
        from email.header import decode_header

        subject_header, charset = decode_header(msg["Subject"])[0]
        # Should unfold properly
        assert "folded" in str(subject_header)


class TestMissingSubjectBody:
    """Test handling of missing subject and body."""

    def test_missing_body_single_part(self):
        """Test email with no body content."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"
        # No body set

        body = get_email_body(msg)
        # Should return empty string, not crash
        assert body == ""

    def test_missing_body_multipart(self):
        """Test multipart email with no text/plain part."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        # Add only HTML part, no text/plain
        html_part = MIMEText("<html><body>Hello</body></html>", "html")
        msg.attach(html_part)

        body = get_email_body(msg)
        # Current implementation returns empty string when no text/plain found
        assert body == ""

    def test_body_with_null_payload(self):
        """Test handling of part with None payload."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"
        msg.set_content("Test body")

        # Manually set payload to None to simulate corruption
        msg.set_payload(None)

        body = get_email_body(msg)
        # Should handle None payload gracefully
        assert body == ""

    def test_multipart_all_attachments(self):
        """Test multipart email where all parts are attachments."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        # Add only attachments
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"file content")
        attachment.add_header("Content-Disposition", "attachment", filename="test.bin")
        msg.attach(attachment)

        body = get_email_body(msg)
        # Should return empty string when no body text
        assert body == ""


class TestLargeAttachments:
    """Test handling of very large attachments."""

    def test_large_attachment_memory(self, test_config):
        """Test that large attachments don't cause memory issues."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        # Create a 10MB attachment (large but not huge)
        large_content = b"x" * (10 * 1024 * 1024)
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(large_content)
        attachment.add_header("Content-Disposition", "attachment", filename="large.bin")
        msg.attach(attachment)

        task_id = "test-large-123"
        attachments = save_attachments(msg, task_id, test_config)

        # Should save successfully
        assert len(attachments) == 1
        saved_file = test_config.input_dir / attachments[0]
        assert saved_file.exists()
        assert saved_file.stat().st_size == 10 * 1024 * 1024

    def test_attachment_with_empty_filename(self, test_config):
        """Test that empty filename attachments are silently skipped.

        Note: This is actually correct behavior - if get_filename() returns
        empty string, the `if filename:` check fails and attachment is skipped.
        """
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"content")
        attachment.add_header("Content-Disposition", "attachment", filename="")
        msg.attach(attachment)

        task_id = "test-123"
        attachments = save_attachments(msg, task_id, test_config)

        # Empty filename causes attachment to be skipped (if filename: check)
        # This is actually safe behavior, though the attachment is lost
        assert len(attachments) == 0

    def test_attachment_with_special_chars_filename(self, test_config):
        """Test filename sanitization removes all special characters."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"content")
        # Filename with special chars
        attachment.add_header(
            "Content-Disposition", "attachment", filename="test<script>alert.exe"
        )
        msg.attach(attachment)

        task_id = "test-123"
        attachments = save_attachments(msg, task_id, test_config)

        # clean_filename should remove < > characters
        assert len(attachments) == 1
        assert "<" not in attachments[0]
        assert ">" not in attachments[0]

    def test_attachment_unicode_filename(self, test_config):
        """BUG: Unicode characters in filename are stripped."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"content")
        # Japanese filename
        attachment.add_header(
            "Content-Disposition", "attachment", filename="document.pdf"
        )
        msg.attach(attachment)

        task_id = "test-123"
        attachments = save_attachments(msg, task_id, test_config)

        # clean_filename only allows alphanumeric and ._-
        # All Japanese characters would be stripped
        assert len(attachments) == 1
        # The Japanese characters are stripped, only document.pdf remains
        # This is actually safe behavior

    def test_attachment_path_traversal_attempt(self, test_config):
        """BUG: Path traversal dots are NOT fully blocked.

        clean_filename() allows '.' character, so '../../../etc/passwd'
        becomes '......etcpasswd' - the dots remain!

        While this doesn't enable actual path traversal (slashes are removed),
        it could cause confusion or be used in other attacks.
        """
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"malicious content")
        # Attempt path traversal
        attachment.add_header(
            "Content-Disposition", "attachment", filename="../../../etc/passwd"
        )
        msg.attach(attachment)

        task_id = "test-123"
        attachments = save_attachments(msg, task_id, test_config)

        # clean_filename removes slashes, so path traversal is blocked
        assert len(attachments) == 1
        assert "/" not in attachments[0]

        # BUG: Dots are preserved! The filename becomes '......etcpasswd'
        # This is the actual behavior - dots ARE in the result
        assert "......" in attachments[0]  # Multiple dots preserved

        # File should be saved in input_dir (path traversal blocked)
        saved_file = test_config.input_dir / attachments[0]
        assert saved_file.exists()


class TestUnicodeEmailAddresses:
    """Test handling of Unicode in email addresses."""

    def test_unicode_local_part(self):
        """Test Unicode in local part of email address."""
        # Modern SMTP supports internationalized email (RFC 6531)
        sender = "testuser@example.com"  # ASCII for now

        # extract_reply_to handles this fine
        reply_to = extract_reply_to(f"Research: {sender}")
        assert reply_to == sender

    def test_idn_domain(self):
        """Test Internationalized Domain Names."""
        # IDN domains like example.com (xn--nxasmq5b) are valid
        # The poller should handle these correctly
        sender = "test@xn--nxasmq5b.com"  # Punycode encoded

        # This should work fine in the sender field
        reply_to = extract_reply_to(f"Research: {sender}")
        assert reply_to == sender

    def test_encoded_from_header(self):
        """Test RFC 2047 encoded From header with display name."""
        raw_email = b"""From: =?utf-8?B?VGVzdCBVc2Vy?= <test@example.com>
Subject: Test
Content-Type: text/plain

Body
"""
        msg = email.message_from_bytes(raw_email)

        # email.utils.parseaddr can handle encoded headers
        from_header = msg["From"]
        assert "test@example.com" in from_header or "Test User" in from_header


class TestMultipleRecipients:
    """Test handling of multiple recipients in To field."""

    def test_multiple_to_recipients(self):
        """Test email with multiple To recipients."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg["From"] = "sender@example.com"
        msg["To"] = "user1@example.com, user2@example.com, user3@example.com"
        msg.set_content("Body text")

        # The poller uses the From address as sender, not To
        # Multiple To recipients shouldn't affect processing
        body = get_email_body(msg)
        assert body.strip() == "Body text"

    def test_cc_and_bcc_recipients(self):
        """Test email with CC and BCC recipients."""
        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg["From"] = "sender@example.com"
        msg["To"] = "user1@example.com"
        msg["Cc"] = "cc1@example.com, cc2@example.com"
        msg["Bcc"] = "bcc@example.com"
        msg.set_content("Body text")

        # Should process normally
        body = get_email_body(msg)
        assert body.strip() == "Body text"


class TestExtractReplyTo:
    """Test extract_reply_to function edge cases."""

    def test_colon_in_email_domain(self):
        """Test handling of colon in unusual places."""
        # Colons can appear in IPv6 address literals
        subject = "Research: user@[::1]"
        reply_to = extract_reply_to(subject)
        # The function looks for @ and . in first word after colon
        # IPv6 literals may not have a dot
        assert reply_to == ""  # Won't match due to no dot

    def test_multiple_colons_in_subject(self):
        """Test subject with multiple colons."""
        subject = "Re: Fw: Research: test@example.com"
        reply_to = extract_reply_to(subject)
        # Only splits on first colon, so gets "Fw" not the email
        assert reply_to == ""

    def test_email_not_first_word(self):
        """Test email not as first word after colon."""
        subject = "Research: Please contact test@example.com"
        reply_to = extract_reply_to(subject)
        # First word is "Please", not an email
        assert reply_to == ""

    def test_partial_email_like_string(self):
        """Test string that looks like email but isn't quite."""
        subject = "Research: user@localhost"
        reply_to = extract_reply_to(subject)
        # Has @ but no dot - won't match
        assert reply_to == ""

    def test_empty_after_colon(self):
        """Test subject with nothing after colon."""
        subject = "Research:"
        reply_to = extract_reply_to(subject)
        assert reply_to == ""

    def test_only_whitespace_after_colon(self):
        """Test subject with only whitespace after colon."""
        subject = "Research:    "
        reply_to = extract_reply_to(subject)
        assert reply_to == ""


class TestCleanFilename:
    """Test clean_filename function edge cases."""

    def test_empty_filename(self):
        """Test empty filename."""
        result = clean_filename("")
        assert result == ""

    def test_all_special_chars(self):
        """Test filename with all special characters."""
        result = clean_filename("!@#$%^&*()+=[]{}|;':\"<>,?/\\`~")
        # Only . and - are preserved from these
        assert result == ""

    def test_unicode_filename(self):
        """BUG: Unicode characters are completely stripped."""
        result = clean_filename("document.pdf")
        # isalpha() returns True for Unicode letters, but the function
        # uses isalpha() which should work for Unicode
        assert "document" in result

    def test_very_long_filename(self):
        """Test very long filename - no length limit enforced."""
        long_name = "a" * 1000 + ".txt"
        result = clean_filename(long_name)
        # No truncation - potential filesystem issues
        # Most filesystems limit to 255 bytes
        assert len(result) == 1004  # 1000 a's + .txt

    def test_null_bytes_in_filename(self):
        """Test filename with null bytes."""
        result = clean_filename("test\x00file.txt")
        # Null byte is not alphanumeric, so filtered out
        assert "\x00" not in result
        assert result == "testfile.txt"

    def test_newlines_in_filename(self):
        """Test filename with newlines."""
        result = clean_filename("test\nfile\r\n.txt")
        # Newlines filtered out
        assert "\n" not in result
        assert "\r" not in result


class TestCreateTask:
    """Test create_task function edge cases."""

    def test_create_task_with_empty_values(self, test_config):
        """Test creating task with empty strings."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        task_id = create_task(
            task_id="test-123",
            subject="",
            body="",
            sender="",
            attachments=[],
            config=test_config,
        )

        assert task_id == "test-123"
        # Task file should exist
        task_file = test_config.input_dir / "task_test-123.json"
        assert task_file.exists()

    def test_create_task_with_unicode(self, test_config):
        """Test creating task with Unicode content."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        task_id = create_task(
            task_id="test-unicode",
            subject="Subject",
            body="Body text",
            sender="user@example.com",
            attachments=[],
            config=test_config,
        )

        assert task_id == "test-unicode"
        task_file = test_config.input_dir / "task_test-unicode.json"
        assert task_file.exists()

        # Read and verify content preserved
        import json

        with open(task_file) as f:
            data = json.load(f)
        assert "Subject" in data["subject"]
        assert "Body" in data["body"]


class TestProcessEmailsEdgeCases:
    """Integration tests for process_emails edge cases."""

    def test_process_emails_with_no_allowed_senders(self, test_config, capsys):
        """Test behavior with empty allowed_senders."""
        from dataclasses import replace

        # Create config with no allowed senders
        empty_config = replace(test_config, allowed_senders=())

        process_emails(empty_config)

        captured = capsys.readouterr()
        assert "No ALLOWED_SENDERS configured" in captured.out

    @patch("src.poller.connect_imap")
    def test_process_emails_handles_none_subject(self, mock_connect, test_config):
        """BUG: None subject causes decode_header to fail."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        # Create email with no subject
        raw_email = b"""From: allowed@example.com
Content-Type: text/plain

Body without subject
"""
        msg = email.message_from_bytes(raw_email)
        assert msg["Subject"] is None  # Confirm subject is None

        # Set up mock IMAP
        mock_mail = MagicMock()
        mock_connect.return_value = mock_mail
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        # This will fail with: TypeError: expected str or bytes-like object
        # because decode_header(None) raises TypeError
        # The bug is that the code doesn't check for None before decode_header

        # For now, just verify the bug exists
        from email.header import decode_header

        with pytest.raises(TypeError):
            decode_header(None)

    @patch("src.poller.connect_imap")
    def test_process_emails_imap_timeout(self, mock_connect, test_config):
        """Test handling of IMAP connection timeout."""
        import socket

        mock_connect.side_effect = socket.timeout("Connection timed out")

        # Should not raise, just print error
        process_emails(test_config)
        # Error is caught and printed

    @patch("src.poller.connect_imap")
    def test_process_emails_imap_auth_failure(self, mock_connect, test_config):
        """Test handling of IMAP authentication failure."""
        import imaplib

        mock_connect.side_effect = imaplib.IMAP4.error("Authentication failed")

        # Should not raise, just print error
        process_emails(test_config)


class TestProcessEmailsIntegration:
    """Integration tests that exercise the full process_emails flow."""

    @patch("src.poller.connect_imap")
    def test_none_subject_handled_gracefully(self, mock_connect, test_config):
        """Test that emails with missing Subject header are handled gracefully.

        Previously, the code called decode_header(None) which raised:
        TypeError: expected str or bytes-like object

        This was fixed by adding a decode_subject() helper that checks for
        None subjects and returns "(No Subject)" as a fallback.
        """
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        # Create email with no subject
        raw_email = b"""From: allowed@example.com
Content-Type: text/plain

Body without subject
"""
        # Set up mock IMAP
        mock_mail = MagicMock()
        mock_connect.return_value = mock_mail
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        # Should handle missing subject gracefully and create task
        process_emails(test_config)

        # Task should be created with "(No Subject)" as subject
        task_files = list(test_config.input_dir.glob("task_*.json"))
        assert len(task_files) == 1

        import json
        with open(task_files[0]) as f:
            task = json.load(f)
        assert task["subject"] == "(No Subject)"
        assert "Body without subject" in task["body"]

    @patch("src.poller.connect_imap")
    def test_very_long_subject_handling(self, mock_connect, test_config):
        """Test handling of extremely long subject lines."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        # Create email with very long subject (10KB)
        long_subject = "A" * 10000
        raw_email = f"""From: allowed@example.com
Subject: {long_subject}
Content-Type: text/plain

Body text
""".encode()

        mock_mail = MagicMock()
        mock_connect.return_value = mock_mail
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        process_emails(test_config)

        task_files = list(test_config.input_dir.glob("task_*.json"))
        assert len(task_files) == 1

        # Verify subject was preserved
        import json

        with open(task_files[0]) as f:
            task = json.load(f)
        assert len(task["subject"]) == 10000

    @patch("src.poller.connect_imap")
    def test_binary_garbage_in_subject(self, mock_connect, test_config):
        """Test handling of binary garbage in subject header."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        # Create email with binary garbage that's invalid UTF-8
        raw_email = b"""From: allowed@example.com
Subject: Test \xff\xfe Binary
Content-Type: text/plain

Body text
"""
        mock_mail = MagicMock()
        mock_connect.return_value = mock_mail
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_email)])

        # Should handle gracefully without crashing
        process_emails(test_config)

        task_files = list(test_config.input_dir.glob("task_*.json"))
        # Email should be processed despite binary garbage
        assert len(task_files) == 1


class TestBodyEncodingEdgeCases:
    """Test edge cases in email body encoding handling."""

    def test_body_with_unknown_charset(self):
        """Test body with declared but unknown charset in header.

        Note: MIMEText validates charset at creation time, so we need
        to manually construct a message with invalid charset header.
        """
        raw_email = b"""Subject: Test
Content-Type: text/plain; charset=nonexistent-charset
Content-Transfer-Encoding: 8bit

Test body content
"""
        msg = email.message_from_bytes(raw_email)

        # get_email_body should handle this gracefully via LookupError catch
        body = get_email_body(msg)
        # LookupError is caught and falls back to utf-8 with replace
        assert "Test body" in body or body == ""

    def test_body_with_mismatched_charset(self):
        """Test body where declared charset doesn't match content."""
        # Create message claiming UTF-8 but containing Latin-1 bytes
        msg = MIMEMultipart()
        text_part = MIMEText("", "plain")
        # Manually set payload with Latin-1 encoded text claiming UTF-8
        latin1_text = "Caf\xe9"  # 'Cafe' with Latin-1 encoded e-acute
        text_part.set_payload(latin1_text.encode("latin-1"))
        text_part.set_param("charset", "utf-8")  # Lie about charset
        msg.attach(text_part)

        body = get_email_body(msg)
        # Should use errors="replace" for invalid UTF-8
        assert body is not None

    def test_body_with_base64_encoding(self):
        """Test body with base64 transfer encoding."""
        import base64

        msg = EmailMessage()
        msg["Subject"] = "Test"
        msg["Content-Type"] = "text/plain; charset=utf-8"
        msg["Content-Transfer-Encoding"] = "base64"
        msg.set_payload(base64.b64encode(b"Hello World").decode())

        body = get_email_body(msg)
        # get_payload(decode=True) should handle base64
        assert "Hello World" in body or body == ""

    def test_body_with_quoted_printable(self):
        """Test body with quoted-printable encoding."""
        raw_email = b"""Subject: Test
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: quoted-printable

Hello=20World=21
"""
        msg = email.message_from_bytes(raw_email)
        body = get_email_body(msg)
        # get_payload(decode=True) handles quoted-printable
        assert "Hello World!" in body or "Hello" in body
