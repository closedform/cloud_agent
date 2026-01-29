"""Tests for src/poller.py"""

import json
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.poller import (
    clean_filename,
    connect_imap,
    create_task,
    extract_reply_to,
    generate_task_id,
    get_email_body,
    process_emails,
    save_attachments,
)


class TestCleanFilename:
    """Tests for clean_filename (sanitize) function."""

    def test_preserves_alphanumeric(self):
        """Should preserve letters and digits."""
        assert clean_filename("file123") == "file123"

    def test_preserves_allowed_punctuation(self):
        """Should preserve dots, underscores, and hyphens."""
        assert clean_filename("file_name-1.txt") == "file_name-1.txt"

    def test_removes_spaces(self):
        """Should remove spaces."""
        assert clean_filename("my file name.txt") == "myfilename.txt"

    def test_removes_special_characters(self):
        """Should remove special characters like @#$%."""
        assert clean_filename("file@#$%.txt") == "file.txt"

    def test_preserves_ascii_letters(self):
        """Should preserve ASCII letters including those from common unicode chars."""
        # clean_filename only checks isalpha() which includes ASCII letters
        # In Python, isalpha() returns True for letters
        assert clean_filename("cafe_resume.txt") == "cafe_resume.txt"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert clean_filename("") == ""

    def test_removes_path_separators(self):
        """Should remove path separators to prevent path traversal."""
        # The function allows dots (.) but removes slashes (/)
        assert clean_filename("../../../etc/passwd") == "......etcpasswd"
        assert clean_filename("folder/file.txt") == "folderfile.txt"

    def test_mixed_safe_and_unsafe(self):
        """Should handle a mix of safe and unsafe characters."""
        assert clean_filename("report [2024] <final>.pdf") == "report2024final.pdf"


class TestExtractReplyTo:
    """Tests for extract_reply_to function."""

    def test_extracts_email_after_colon(self):
        """Should extract email address after colon in subject."""
        subject = "Research: user@example.com"
        assert extract_reply_to(subject) == "user@example.com"

    def test_extracts_email_with_additional_text(self):
        """Should extract only the email, ignoring additional text."""
        subject = "Research: user@example.com some other text"
        assert extract_reply_to(subject) == "user@example.com"

    def test_returns_empty_for_no_colon(self):
        """Should return empty string if no colon in subject."""
        subject = "Just a regular subject"
        assert extract_reply_to(subject) == ""

    def test_returns_empty_for_no_email_after_colon(self):
        """Should return empty string if text after colon is not an email."""
        subject = "Status: pending"
        assert extract_reply_to(subject) == ""

    def test_returns_empty_for_invalid_email(self):
        """Should return empty string for text that lacks @ or dot."""
        subject = "Task: invalid-email"
        assert extract_reply_to(subject) == ""

    def test_handles_multiple_colons(self):
        """Should use first colon for splitting."""
        subject = "Re: Fwd: Research: user@example.com"
        assert extract_reply_to(subject) == ""  # "Fwd" doesn't contain @

    def test_returns_empty_for_empty_after_colon(self):
        """Should return empty string if nothing after colon."""
        subject = "Research:"
        assert extract_reply_to(subject) == ""

    def test_handles_whitespace_after_colon(self):
        """Should handle extra whitespace."""
        subject = "Research:   user@domain.com"
        assert extract_reply_to(subject) == "user@domain.com"


class TestGenerateTaskId:
    """Tests for generate_task_id function."""

    def test_returns_hex_string(self):
        """Should return a hexadecimal string."""
        task_id = generate_task_id()
        assert all(c in "0123456789abcdef" for c in task_id)

    def test_returns_32_char_string(self):
        """Should return 32-character hex string (UUID4 without hyphens)."""
        task_id = generate_task_id()
        assert len(task_id) == 32

    def test_unique_ids(self):
        """Should generate unique IDs on each call."""
        ids = [generate_task_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestGetEmailBody:
    """Tests for get_email_body function."""

    def test_simple_text_message(self):
        """Should extract body from simple text message."""
        msg = EmailMessage()
        msg.set_content("Hello, this is the body.")
        body = get_email_body(msg)
        assert "Hello, this is the body." in body

    def test_multipart_with_plain_text(self):
        """Should extract plain text from multipart message."""
        msg = MIMEMultipart("alternative")
        text_part = MIMEText("Plain text body", "plain")
        html_part = MIMEText("<html><body>HTML body</body></html>", "html")
        msg.attach(text_part)
        msg.attach(html_part)
        body = get_email_body(msg)
        assert "Plain text body" in body

    def test_html_only_message_returns_empty(self):
        """Should return empty string for HTML-only message (no text/plain)."""
        msg = MIMEMultipart()
        html_part = MIMEText("<html><body>HTML only</body></html>", "html")
        msg.attach(html_part)
        body = get_email_body(msg)
        assert body == ""

    def test_multipart_with_attachment(self):
        """Should skip attachments and extract text body."""
        msg = MIMEMultipart()
        text_part = MIMEText("The actual body", "plain")
        msg.attach(text_part)

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"file content")
        attachment.add_header(
            "Content-Disposition", "attachment", filename="document.pdf"
        )
        msg.attach(attachment)

        body = get_email_body(msg)
        assert "The actual body" in body

    def test_utf8_encoding(self):
        """Should handle UTF-8 encoded messages."""
        msg = EmailMessage()
        msg.set_content("Cafe avec creme")
        body = get_email_body(msg)
        assert "Cafe" in body

    def test_iso_8859_1_encoding(self):
        """Should handle ISO-8859-1 encoded messages."""
        msg = MIMEText("Cafe".encode("iso-8859-1"), "plain", "iso-8859-1")
        body = get_email_body(msg)
        assert "Caf" in body

    def test_handles_decode_error(self):
        """Should handle decode errors gracefully."""
        msg = MIMEMultipart()
        text_part = MIMEText("test", "plain")
        # Manually set payload with bad encoding
        text_part._payload = b"\xff\xfe"  # Invalid UTF-8
        text_part.set_param("charset", "utf-8")
        msg.attach(text_part)
        body = get_email_body(msg)
        # Should not raise, returns replacement chars or empty
        assert isinstance(body, str)

    def test_handles_unknown_charset(self):
        """Should handle unknown charset gracefully."""
        msg = MIMEText("test content", "plain")
        msg.set_param("charset", "nonexistent-charset")
        body = get_email_body(msg)
        # Should fallback to utf-8
        assert isinstance(body, str)

    def test_empty_payload(self):
        """Should handle empty payload."""
        msg = EmailMessage()
        msg.set_content("")
        body = get_email_body(msg)
        # EmailMessage.set_content("") actually adds a newline
        assert body.strip() == ""

    def test_nested_multipart(self):
        """Should handle nested multipart messages."""
        outer = MIMEMultipart("mixed")
        inner = MIMEMultipart("alternative")
        text_part = MIMEText("Nested text body", "plain")
        inner.attach(text_part)
        outer.attach(inner)
        body = get_email_body(outer)
        assert "Nested text body" in body


class TestSaveAttachments:
    """Tests for save_attachments function."""

    def test_saves_single_attachment(self, test_config, temp_dir):
        """Should save a single attachment."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart()
        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"PDF content here")
        attachment.add_header(
            "Content-Disposition", "attachment", filename="document.pdf"
        )
        msg.attach(attachment)

        task_id = "test123"
        attachments = save_attachments(msg, task_id, test_config)

        assert len(attachments) == 1
        assert attachments[0] == "test123_document.pdf"
        saved_file = temp_dir / "test123_document.pdf"
        assert saved_file.exists()
        assert saved_file.read_bytes() == b"PDF content here"

    def test_sanitizes_attachment_filename(self, test_config, temp_dir):
        """Should sanitize attachment filenames."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart()
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"content")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename="unsafe file@name!.txt",
        )
        msg.attach(attachment)

        attachments = save_attachments(msg, "task1", test_config)
        assert len(attachments) == 1
        # Should have sanitized filename
        assert "!" not in attachments[0]
        assert "@" not in attachments[0]

    def test_skips_multipart_parts(self, test_config, temp_dir):
        """Should skip multipart container parts."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart("mixed")
        inner = MIMEMultipart("alternative")
        text = MIMEText("body text", "plain")
        inner.attach(text)
        msg.attach(inner)

        attachments = save_attachments(msg, "task1", test_config)
        assert attachments == []

    def test_skips_parts_without_disposition(self, test_config, temp_dir):
        """Should skip parts without Content-Disposition."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart()
        text = MIMEText("body text", "plain")
        msg.attach(text)

        attachments = save_attachments(msg, "task1", test_config)
        assert attachments == []

    def test_handles_no_filename(self, test_config, temp_dir):
        """Should skip attachments without filename."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart()
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"content")
        attachment.add_header("Content-Disposition", "attachment")
        msg.attach(attachment)

        attachments = save_attachments(msg, "task1", test_config)
        assert attachments == []


class TestCreateTask:
    """Tests for create_task function."""

    def test_creates_task_file(self, test_config, temp_dir):
        """Should create a task JSON file in input directory."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        task_id = create_task(
            task_id="abc123",
            subject="Test Subject",
            body="Test body",
            sender="sender@example.com",
            attachments=[],
            config=test_config,
        )

        assert task_id == "abc123"
        task_file = temp_dir / "task_abc123.json"
        assert task_file.exists()

        with open(task_file) as f:
            data = json.load(f)

        assert data["id"] == "abc123"
        assert data["subject"] == "Test Subject"
        assert data["body"] == "Test body"
        assert data["sender"] == "sender@example.com"
        assert data["reply_to"] == "sender@example.com"

    def test_extracts_reply_to_from_subject(self, test_config, temp_dir):
        """Should extract reply_to email from subject pattern."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        task_id = create_task(
            task_id="task1",
            subject="Research: other@example.com",
            body="Research request",
            sender="sender@example.com",
            attachments=[],
            config=test_config,
        )

        task_file = temp_dir / "task_task1.json"
        with open(task_file) as f:
            data = json.load(f)

        assert data["reply_to"] == "other@example.com"
        assert data["sender"] == "sender@example.com"

    def test_uses_sender_when_no_reply_to_in_subject(self, test_config, temp_dir):
        """Should use sender as reply_to when not specified in subject."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        create_task(
            task_id="task2",
            subject="Regular subject line",
            body="Body content",
            sender="original@sender.com",
            attachments=[],
            config=test_config,
        )

        task_file = temp_dir / "task_task2.json"
        with open(task_file) as f:
            data = json.load(f)

        assert data["reply_to"] == "original@sender.com"

    def test_includes_attachments_list(self, test_config, temp_dir):
        """Should include attachments list in task."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        create_task(
            task_id="task3",
            subject="With attachments",
            body="Body",
            sender="sender@example.com",
            attachments=["task3_file1.pdf", "task3_file2.png"],
            config=test_config,
        )

        task_file = temp_dir / "task_task3.json"
        with open(task_file) as f:
            data = json.load(f)

        assert data["attachments"] == ["task3_file1.pdf", "task3_file2.png"]


class TestConnectImap:
    """Tests for connect_imap function."""

    def test_connects_and_logs_in(self, test_config):
        """Should connect to IMAP server and login with timeout."""
        with patch("src.poller.imaplib.IMAP4_SSL") as mock_imap:
            mock_mail = MagicMock()
            mock_imap.return_value = mock_mail

            result = connect_imap(test_config)

            # Should use per-connection timeout parameter (not global socket timeout)
            mock_imap.assert_called_once_with(test_config.imap_server, timeout=30)
            mock_mail.login.assert_called_once_with(
                test_config.email_user, test_config.email_pass
            )
            assert result == mock_mail

    def test_cleans_up_on_login_failure(self, test_config):
        """Should logout and clean up when login fails."""
        with patch("src.poller.imaplib.IMAP4_SSL") as mock_imap:
            mock_mail = MagicMock()
            mock_mail.login.side_effect = Exception("Auth failed")
            mock_imap.return_value = mock_mail

            with pytest.raises(Exception, match="Auth failed"):
                connect_imap(test_config)

            # Should attempt logout on failure
            mock_mail.logout.assert_called_once()


class TestProcessEmails:
    """Tests for process_emails function."""

    def test_warns_when_no_allowed_senders(self, test_config, capsys):
        """Should warn when no allowed senders configured."""
        empty_config = test_config.__class__(
            **{**test_config.__dict__, "allowed_senders": ()}
        )

        process_emails(empty_config)

        captured = capsys.readouterr()
        assert "Warning: No ALLOWED_SENDERS configured" in captured.out

    def test_handles_imap_connection_error(self, test_config, capsys):
        """Should handle IMAP connection errors gracefully."""
        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            process_emails(test_config)

            captured = capsys.readouterr()
            assert "Email Error: Connection failed" in captured.out

    def test_processes_unread_emails(self, test_config, temp_dir, capsys):
        """Should process unread emails from allowed senders."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        # Create a proper email message
        msg = EmailMessage()
        msg["Subject"] = "Test Email"
        msg["From"] = "allowed@example.com"
        msg.set_content("Email body content")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            process_emails(test_config)

            mock_mail.select.assert_called_once_with("inbox")
            mock_mail.search.assert_called_once()
            mock_mail.close.assert_called_once()
            mock_mail.logout.assert_called_once()

        captured = capsys.readouterr()
        assert "Received: Test Email" in captured.out
        assert "Created task" in captured.out

    def test_handles_unicode_subject(self, test_config, temp_dir, capsys):
        """Should handle Unicode subjects correctly."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        msg["Subject"] = "=?UTF-8?B?Q2Fmw6kgTWVldGluZw==?="  # "Cafe Meeting" encoded
        msg["From"] = "allowed@example.com"
        msg.set_content("Body")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        captured = capsys.readouterr()
        # Should decode the subject
        assert "Received:" in captured.out

    def test_handles_missing_subject(self, test_config, temp_dir, capsys):
        """Should handle emails with missing Subject header."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        # No Subject header
        msg["From"] = "allowed@example.com"
        msg.set_content("Body without subject")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            # Should not raise
            process_emails(test_config)

    def test_handles_no_new_emails(self, test_config, capsys):
        """Should handle case with no new emails."""
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b""])  # Empty result

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            process_emails(test_config)

            mock_mail.fetch.assert_not_called()

    def test_closes_connection_on_error(self, test_config):
        """Should close connection even when error occurs."""
        mock_mail = MagicMock()
        mock_mail.search.side_effect = Exception("Search failed")

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            process_emails(test_config)

            mock_mail.close.assert_called_once()
            mock_mail.logout.assert_called_once()

    def test_handles_multipart_email(self, test_config, temp_dir, capsys):
        """Should handle multipart emails correctly."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Multipart Test"
        msg["From"] = "allowed@example.com"
        text_part = MIMEText("Plain text version", "plain")
        html_part = MIMEText("<html><body>HTML version</body></html>", "html")
        msg.attach(text_part)
        msg.attach(html_part)

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        # Should have created a task file
        task_files = list(temp_dir.glob("task_*.json"))
        assert len(task_files) == 1

        with open(task_files[0]) as f:
            data = json.load(f)

        assert "Plain text version" in data["body"]

    def test_processes_multiple_senders(self, test_config, temp_dir):
        """Should check emails from all allowed senders."""
        multi_sender_config = test_config.__class__(
            **{
                **test_config.__dict__,
                "allowed_senders": ("sender1@test.com", "sender2@test.com"),
                "input_dir": temp_dir,
            }
        )
        temp_dir.mkdir(exist_ok=True)

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b""])  # No emails

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            process_emails(multi_sender_config)

            # Should search for each sender
            assert mock_mail.search.call_count == 2

    def test_handles_email_with_attachments(self, test_config, temp_dir, capsys):
        """Should save email attachments."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = MIMEMultipart()
        msg["Subject"] = "Email with attachment"
        msg["From"] = "allowed@example.com"
        text_part = MIMEText("Body text", "plain")
        msg.attach(text_part)

        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"PDF content")
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition", "attachment", filename="report.pdf"
        )
        msg.attach(attachment)

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        captured = capsys.readouterr()
        assert "Saved attachment:" in captured.out

        # Check attachment was saved
        attachment_files = [
            f for f in temp_dir.iterdir() if "report.pdf" in f.name
        ]
        assert len(attachment_files) == 1


class TestSubjectDecoding:
    """Tests for email subject decoding behavior."""

    def test_plain_ascii_subject(self, test_config, temp_dir):
        """Should handle plain ASCII subjects."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        msg["Subject"] = "Simple ASCII Subject"
        msg["From"] = "allowed@example.com"
        msg.set_content("Body")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        task_files = list(temp_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            data = json.load(f)

        assert data["subject"] == "Simple ASCII Subject"

    def test_base64_encoded_subject(self, test_config, temp_dir):
        """Should decode base64 encoded subjects."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        # "Meeting Tomorrow" in base64
        msg["Subject"] = "=?UTF-8?B?TWVldGluZyBUb21vcnJvdw==?="
        msg["From"] = "allowed@example.com"
        msg.set_content("Body")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        task_files = list(temp_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            data = json.load(f)

        assert data["subject"] == "Meeting Tomorrow"

    def test_quoted_printable_subject(self, test_config, temp_dir):
        """Should decode quoted-printable subjects."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        # "Resume" with e-acute in quoted-printable
        msg["Subject"] = "=?UTF-8?Q?R=C3=A9sum=C3=A9?="
        msg["From"] = "allowed@example.com"
        msg.set_content("Body")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        task_files = list(temp_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            data = json.load(f)

        # Should decode the accented characters
        assert "sum" in data["subject"]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_email_body(self, test_config, temp_dir):
        """Should handle emails with empty body."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        msg = EmailMessage()
        msg["Subject"] = "Empty body email"
        msg["From"] = "allowed@example.com"
        msg.set_content("")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        task_files = list(temp_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            data = json.load(f)

        # EmailMessage.set_content("") actually adds a newline
        assert data["body"].strip() == ""

    def test_very_long_subject(self, test_config, temp_dir):
        """Should handle very long subjects."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        long_subject = "A" * 1000

        msg = EmailMessage()
        msg["Subject"] = long_subject
        msg["From"] = "allowed@example.com"
        msg.set_content("Body")

        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail
            process_emails(test_config)

        task_files = list(temp_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            data = json.load(f)

        assert len(data["subject"]) == 1000

    def test_logout_error_does_not_raise(self, test_config):
        """Should handle logout errors gracefully."""
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b""])
        mock_mail.logout.side_effect = Exception("Logout failed")

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            # Should not raise
            process_emails(test_config)

    def test_close_error_does_not_raise(self, test_config):
        """Should handle close errors gracefully."""
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b""])
        mock_mail.close.side_effect = Exception("Close failed")

        with patch("src.poller.connect_imap") as mock_connect:
            mock_connect.return_value = mock_mail

            # Should not raise
            process_emails(test_config)
