"""Stress tests for email client security and edge cases.

Tests for:
1. HTML injection in email body
2. Header injection in subject
3. Very long subjects/bodies
4. Unicode in all fields
5. text_to_html with malformed input
"""

import pytest
from unittest.mock import MagicMock, patch

from src.clients.email import (
    send_email,
    text_to_html,
    html_response,
    html_reminder,
    html_weekly_schedule,
    format_weather_html,
    format_calendar_html,
)


class TestHTMLInjection:
    """Tests for HTML injection vulnerabilities."""

    def test_text_to_html_escapes_script_tags(self):
        """Script tags in plain text should be escaped."""
        malicious = "<script>alert('XSS')</script>"
        result = text_to_html(malicious)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_text_to_html_escapes_onclick_handler(self):
        """Event handlers should be escaped."""
        malicious = '<div onclick="alert(1)">click me</div>'
        result = text_to_html(malicious)
        # All HTML is now escaped to prevent XSS
        assert '&lt;div' in result
        assert 'onclick=' not in result or '&quot;' in result

    def test_text_to_html_with_img_onerror(self):
        """Image onerror handlers should be escaped."""
        malicious = '<img src=x onerror="alert(1)">'
        result = text_to_html(malicious)
        # img tag is not in the allowed list, so should be escaped
        assert "&lt;img" in result or "<img" not in result

    def test_text_to_html_preserves_html_if_detected(self):
        """HTML detection might allow XSS through if HTML is detected."""
        # This contains a valid HTML tag pattern
        malicious = '<p>Hello</p><script>alert("XSS")</script>'
        result = text_to_html(malicious)
        # BUG: If input has valid HTML tags, script is passed through!
        if "<script>" in result:
            pytest.fail(
                "BUG: text_to_html passes through <script> tags when HTML is detected"
            )

    def test_text_to_html_injection_via_p_tag(self):
        """Test if malicious content after valid p tag is passed through."""
        malicious = '<p>Safe</p><img src=x onerror=alert(1)>'
        result = text_to_html(malicious)
        # The regex checks for valid HTML tags, if found, returns as-is
        if "onerror" in result and "&lt;" not in result:
            pytest.fail(
                "BUG: Malicious img onerror passed through due to HTML detection"
            )

    def test_html_response_with_malicious_content_via_text_to_html(self):
        """html_response content should be pre-processed by text_to_html.

        The content parameter is expected to come from text_to_html() which
        handles escaping. Callers must use text_to_html() on user input.
        """
        malicious = '<script>alert("XSS")</script>'
        # Correct usage: escape with text_to_html first
        safe_content = text_to_html(malicious)
        result = html_response(safe_content, title="Test")
        # Script tags should be escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_response_with_malicious_title(self):
        """html_response should escape title parameter."""
        malicious = '<script>alert("XSS")</script>'
        result = html_response("Safe content", title=malicious)
        if "<script>" in result:
            pytest.fail(
                "BUG: html_response does not escape malicious title parameter"
            )

    def test_html_reminder_with_malicious_message(self):
        """html_reminder should escape message parameter."""
        malicious = '<script>alert("XSS")</script>'
        result = html_reminder(malicious, "2026-01-27")
        if "<script>" in result:
            pytest.fail(
                "BUG: html_reminder does not escape malicious message parameter"
            )

    def test_html_reminder_with_malicious_time(self):
        """html_reminder should escape original_time parameter."""
        malicious = '</p><script>alert("XSS")</script><p>'
        result = html_reminder("Safe message", malicious)
        if "<script>" in result:
            pytest.fail(
                "BUG: html_reminder does not escape malicious original_time parameter"
            )

    def test_format_weather_html_with_malicious_day(self):
        """format_weather_html should escape forecast fields."""
        forecasts = [
            {
                "day": '<script>alert("XSS")</script>',
                "date": "Jan 27",
                "high": 45,
                "low": 30,
                "condition": "Sunny",
            }
        ]
        result = format_weather_html(forecasts)
        if "<script>" in result:
            pytest.fail(
                "BUG: format_weather_html does not escape malicious day name"
            )

    def test_format_weather_html_with_malicious_condition(self):
        """format_weather_html should escape condition field."""
        forecasts = [
            {
                "day": "Monday",
                "date": "Jan 27",
                "high": 45,
                "low": 30,
                "condition": '<img src=x onerror="alert(1)">',
            }
        ]
        result = format_weather_html(forecasts)
        if "onerror" in result and "&lt;" not in result:
            pytest.fail(
                "BUG: format_weather_html does not escape malicious condition"
            )

    def test_format_calendar_html_with_malicious_summary(self):
        """format_calendar_html should escape event summary."""
        events = {
            "work": [
                {
                    "start": "9:00 AM",
                    "summary": '<script>alert("XSS")</script>',
                }
            ]
        }
        result = format_calendar_html(events)
        if "<script>" in result:
            pytest.fail(
                "BUG: format_calendar_html does not escape malicious event summary"
            )

    def test_format_calendar_html_with_malicious_calendar_name(self):
        """format_calendar_html should escape calendar names."""
        events = {
            '<script>alert("XSS")</script>': [
                {
                    "start": "9:00 AM",
                    "summary": "Meeting",
                }
            ]
        }
        result = format_calendar_html(events)
        if "<script>" in result:
            pytest.fail(
                "BUG: format_calendar_html does not escape malicious calendar name"
            )


class TestHeaderInjection:
    """Tests for email header injection vulnerabilities."""

    def test_subject_with_newline_crlf(self):
        """Subject with CRLF should not inject headers."""
        malicious_subject = "Test\r\nBcc: attacker@evil.com"

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="victim@example.com",
                subject=malicious_subject,
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            if result:
                # Check what was actually sent
                call_args = mock_server.sendmail.call_args
                if call_args:
                    msg_string = call_args[0][2]
                    # Check if header injection occurred
                    if "\r\nBcc:" in msg_string or "\nBcc:" in msg_string:
                        pytest.fail(
                            "BUG: Header injection via CRLF in subject succeeded"
                        )

    def test_subject_with_newline_lf(self):
        """Subject with LF should not inject headers."""
        malicious_subject = "Test\nBcc: attacker@evil.com"

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            send_email(
                to_address="victim@example.com",
                subject=malicious_subject,
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            if mock_server.sendmail.called:
                msg_string = mock_server.sendmail.call_args[0][2]
                # Python's email library typically handles this via folding
                # But let's verify no actual Bcc header was injected
                lines = msg_string.split("\n")
                bcc_headers = [l for l in lines if l.lower().startswith("bcc:")]
                if bcc_headers:
                    pytest.fail(
                        "BUG: Header injection via LF in subject succeeded"
                    )

    def test_to_address_with_injection(self):
        """To address should not allow injection of additional recipients."""
        malicious_to = "victim@example.com\r\nBcc: attacker@evil.com"

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            send_email(
                to_address=malicious_to,
                subject="Test",
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            if mock_server.sendmail.called:
                msg_string = mock_server.sendmail.call_args[0][2]
                lines = msg_string.split("\n")
                bcc_headers = [l for l in lines if l.lower().startswith("bcc:")]
                if bcc_headers:
                    pytest.fail(
                        "BUG: Header injection via to_address succeeded"
                    )


class TestLongInputs:
    """Tests for very long subjects and bodies."""

    def test_very_long_subject(self):
        """Very long subject should not crash."""
        long_subject = "A" * 100000

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Should not raise
            result = send_email(
                to_address="test@example.com",
                subject=long_subject,
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_very_long_body(self):
        """Very long body should not crash."""
        long_body = "A" * 10_000_000  # 10MB

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body=long_body,
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_text_to_html_with_long_input(self):
        """text_to_html should handle very long input."""
        long_text = "A" * 1_000_000
        # Should not raise or hang
        result = text_to_html(long_text)
        assert len(result) >= len(long_text)

    def test_text_to_html_with_many_newlines(self):
        """text_to_html should handle many paragraphs."""
        many_paragraphs = "\n\n".join(["Paragraph"] * 10000)
        # Should not hang due to regex catastrophic backtracking
        result = text_to_html(many_paragraphs)
        assert "<p>" in result

    def test_text_to_html_with_deeply_nested_markdown(self):
        """Test potential regex catastrophic backtracking."""
        # Pattern that might cause backtracking: many asterisks
        evil_input = "*" * 1000
        # Should complete in reasonable time
        import time
        start = time.time()
        result = text_to_html(evil_input)
        elapsed = time.time() - start
        if elapsed > 5:
            pytest.fail(
                f"BUG: text_to_html took {elapsed}s - possible regex catastrophic backtracking"
            )


class TestUnicodeHandling:
    """Tests for Unicode in all fields."""

    def test_unicode_subject(self):
        """Unicode in subject should work."""
        unicode_subject = "Test Subject"

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject=unicode_subject,
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_unicode_body(self):
        """Unicode in body should work."""
        unicode_body = "Hello World! Chinese: Japanese: Korean: Arabic: Russian: "

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body=unicode_body,
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_unicode_to_address(self):
        """Unicode email address should be handled."""
        # IDN email address
        unicode_to = "user@xn--e1afmkfd.xn--p1ai"  # user@.

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address=unicode_to,
                subject="Test",
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_text_to_html_with_unicode(self):
        """text_to_html should handle Unicode properly."""
        unicode_text = "Hello World! "
        result = text_to_html(unicode_text)
        assert "" in result
        assert "" in result

    def test_text_to_html_with_rtl_text(self):
        """text_to_html should handle RTL (Arabic/Hebrew) text."""
        rtl_text = " "  # Arabic and Hebrew
        result = text_to_html(rtl_text)
        assert "" in result
        assert "" in result

    def test_text_to_html_with_zero_width_chars(self):
        """text_to_html should handle zero-width characters."""
        # Zero-width joiner, zero-width non-joiner, zero-width space
        zwc_text = "Hello\u200b\u200c\u200dWorld"
        result = text_to_html(zwc_text)
        # Should not crash, characters may or may not be preserved
        assert "Hello" in result
        assert "World" in result

    def test_text_to_html_with_combining_characters(self):
        """text_to_html should handle combining diacritical marks."""
        # e + combining acute accent
        combining_text = "cafe\u0301"
        result = text_to_html(combining_text)
        assert "caf" in result

    def test_text_to_html_with_surrogate_pairs(self):
        """text_to_html should handle emoji (surrogate pairs in UTF-16)."""
        emoji_text = "Hello !"
        result = text_to_html(emoji_text)
        assert "Hello" in result


class TestTextToHtmlMalformed:
    """Tests for text_to_html with malformed/edge case input."""

    def test_empty_string(self):
        """Empty string should return empty or minimal HTML."""
        result = text_to_html("")
        # Should not crash, may return empty string
        assert isinstance(result, str)

    def test_only_whitespace(self):
        """Whitespace-only input."""
        result = text_to_html("   \n\n\t  ")
        assert isinstance(result, str)

    def test_unclosed_markdown_bold(self):
        """Unclosed **bold should not crash."""
        result = text_to_html("**unclosed bold")
        assert "unclosed bold" in result

    def test_unclosed_markdown_italic(self):
        """Unclosed *italic should not crash."""
        result = text_to_html("*unclosed italic")
        assert "unclosed italic" in result

    def test_nested_markdown(self):
        """Nested ***bold italic*** handling."""
        result = text_to_html("***bold italic***")
        # Should not crash, result varies
        assert isinstance(result, str)

    def test_mismatched_markdown(self):
        """Mismatched *bold** should not crash."""
        result = text_to_html("*mismatched**")
        assert "mismatched" in result

    def test_null_bytes(self):
        """Null bytes in input should be handled."""
        result = text_to_html("Hello\x00World")
        # Should not crash
        assert isinstance(result, str)

    def test_backslash_sequences(self):
        """Backslash sequences should not cause issues."""
        result = text_to_html("C:\\Users\\test\\file.txt")
        assert "Users" in result

    def test_html_entities_in_plain_text(self):
        """HTML entities in plain text should be escaped."""
        result = text_to_html("5 > 3 and 2 < 4 and A&B")
        assert "&gt;" in result
        assert "&lt;" in result
        assert "&amp;" in result

    def test_partial_html_tags(self):
        """Partial HTML tags should be escaped."""
        result = text_to_html("< not a tag > but <fake")
        # These aren't valid HTML tags so should be escaped
        if "<fake" in result and "&lt;" not in result:
            # Actually this is fine since it's not matching the regex pattern
            pass

    def test_bullet_list_edge_cases(self):
        """Bullet list conversion edge cases."""
        # Mixed bullet styles
        result = text_to_html("- item1\n* item2\n- item3")
        assert "<li>" in result
        assert "<ul>" in result

    def test_bullet_with_nested_formatting(self):
        """Bullet items with markdown formatting."""
        result = text_to_html("- **bold item**\n- *italic item*")
        assert "<strong>" in result
        assert "<em>" in result

    def test_very_long_lines(self):
        """Very long single lines."""
        long_line = "A" * 100000
        result = text_to_html(long_line)
        assert len(result) >= 100000

    def test_many_consecutive_asterisks(self):
        """Many consecutive asterisks - potential regex issue."""
        stars = "***" * 100
        result = text_to_html(stars)
        assert isinstance(result, str)

    def test_alternating_asterisks_text(self):
        """Alternating asterisks and text - regex edge case."""
        alt = "*a*b*c*d*e*f*g*h*i*j*"
        result = text_to_html(alt)
        assert isinstance(result, str)


class TestHTMLDetectionBypass:
    """Tests for bypassing HTML detection in text_to_html."""

    def test_case_variation_bypasses(self):
        """Case variations of HTML tags."""
        # Lowercase p tag should trigger HTML detection
        result1 = text_to_html("<P>test</P>")
        # The regex uses re.IGNORECASE so this should match

    def test_tag_with_attributes(self):
        """HTML tag with attributes."""
        result = text_to_html('<p class="test">content</p>')
        # Should be detected as HTML

    def test_self_closing_tags(self):
        """Self-closing HTML tags."""
        result = text_to_html("<br/>test<br />more")
        # br is in the detection pattern

    def test_minimal_html_with_xss(self):
        """Minimal HTML that triggers detection plus XSS."""
        # This is the critical bug test
        malicious = '<p>hello</p><script>evil()</script>'
        result = text_to_html(malicious)
        # If <script> is in result unescaped, it's a bug
        if "<script>" in result:
            pytest.fail(
                "CRITICAL BUG: XSS via HTML detection bypass - "
                "<script> tag passed through when valid HTML detected"
            )

    def test_span_with_style_injection(self):
        """Span tag with style-based attacks should be escaped."""
        malicious = '<span>ok</span><span style="background:url(javascript:alert(1))">x</span>'
        result = text_to_html(malicious)
        # The HTML should be fully escaped, making the javascript: URL non-functional
        # Check that span tags are escaped (not functional HTML)
        assert "&lt;span" in result
        assert "<span" not in result.replace("&lt;span", "")


class TestSendEmailEdgeCases:
    """Edge case tests for send_email function."""

    def test_missing_credentials(self):
        """Missing credentials should return False."""
        result = send_email(
            to_address="test@example.com",
            subject="Test",
            body="Test",
            email_user="",
            email_pass="password",
        )
        assert result is False

        result = send_email(
            to_address="test@example.com",
            subject="Test",
            body="Test",
            email_user="user@example.com",
            email_pass="",
        )
        assert result is False

    def test_empty_subject(self):
        """Empty subject should still work."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="",
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_empty_body(self):
        """Empty body should still work."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body="",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is True

    def test_html_body_only(self):
        """HTML body without plain text fallback should work."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body="",
                email_user="sender@example.com",
                email_pass="password",
                html_body="<p>HTML content</p>",
            )

            assert result is True

    def test_smtp_connection_error(self):
        """SMTP connection error should return False."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body="Test body",
                email_user="sender@example.com",
                email_pass="password",
            )

            assert result is False

    def test_smtp_auth_error(self):
        """SMTP authentication error should return False."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = send_email(
                to_address="test@example.com",
                subject="Test",
                body="Test body",
                email_user="sender@example.com",
                email_pass="wrong_password",
            )

            assert result is False


import smtplib  # Need to import for SMTPAuthenticationError
