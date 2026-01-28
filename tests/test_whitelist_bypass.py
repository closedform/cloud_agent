"""Security tests for recipient whitelist bypass attempts.

These tests verify that the recipient whitelist cannot be bypassed
using various techniques like case variations, Unicode lookalikes,
whitespace padding, or display name formats.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.agents.tools.task_tools import create_agent_task
from src.agents.tools._context import set_request_context, clear_request_context


@pytest.fixture
def mock_config_with_whitelist():
    """Create a mock config with a specific allowed sender."""
    config = MagicMock()
    config.allowed_senders = ("allowed@example.com", "admin@test.org")
    config.input_dir = MagicMock()
    return config


@pytest.fixture
def setup_request_context():
    """Set up request context for tool calls."""
    set_request_context(
        user_email="attacker@example.com",
        thread_id="test-thread-123",
        reply_to="attacker@example.com",
        body="test body",
    )
    yield
    clear_request_context()


class TestCaseVariationBypass:
    """Test that case variations in email addresses are blocked."""

    @pytest.mark.parametrize("email_variant", [
        "ALLOWED@example.com",        # All caps local part
        "Allowed@example.com",        # Title case local part
        "allowed@EXAMPLE.COM",        # All caps domain
        "allowed@Example.Com",        # Title case domain
        "ALLOWED@EXAMPLE.COM",        # All caps
        "AllOwEd@ExAmPlE.cOm",        # Mixed case
    ])
    def test_case_variations_should_be_blocked(
        self, mock_config_with_whitelist, setup_request_context, email_variant
    ):
        """Case variations should NOT bypass the whitelist.

        VULNERABILITY: If this test fails (returns success), it means the
        whitelist can be bypassed using case variations.
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": email_variant,
                    "subject": "Test",
                    "body": "Test body",
                },
                created_by="test",
            )

            # If the whitelist is case-insensitive (secure), all these should fail
            # If it's case-sensitive (vulnerable), uppercase variants will fail
            # but this test documents the expected secure behavior
            assert result["status"] == "error", (
                f"VULNERABILITY: Case variation '{email_variant}' bypassed whitelist! "
                f"Expected error, got: {result}"
            )


class TestUnicodeBypass:
    """Test that Unicode lookalike characters are blocked."""

    @pytest.mark.parametrize("email_with_unicode,description", [
        # Cyrillic lookalikes
        ("аllowed@example.com", "Cyrillic 'а' instead of Latin 'a'"),
        ("allоwed@example.com", "Cyrillic 'о' instead of Latin 'o'"),
        ("allowed@еxample.com", "Cyrillic 'е' instead of Latin 'e'"),
        ("allowed@examplе.com", "Cyrillic 'е' at end of 'example'"),

        # Full-width characters
        ("allowed@example.com", "Full-width '@' (U+FF20)"),
        ("allowed@example。com", "Full-width period (U+3002)"),

        # Other Unicode tricks
        ("allowed@example\u200b.com", "Zero-width space in domain"),
        ("allowed\u200b@example.com", "Zero-width space before @"),
        ("allowed@example.com\u200b", "Zero-width space at end"),

        # Homograph attacks
        ("allowed@examp1e.com", "Number 1 instead of letter l"),
        ("all0wed@example.com", "Number 0 instead of letter o"),
    ])
    def test_unicode_lookalikes_should_be_blocked(
        self, mock_config_with_whitelist, setup_request_context, email_with_unicode, description
    ):
        """Unicode lookalike characters should NOT bypass the whitelist.

        VULNERABILITY: If this test fails, homograph attacks can bypass the whitelist.
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": email_with_unicode,
                    "subject": "Test",
                    "body": "Test body",
                },
                created_by="test",
            )

            # These should all be blocked (return error)
            assert result["status"] == "error", (
                f"VULNERABILITY: Unicode attack ({description}) - "
                f"'{email_with_unicode}' was NOT blocked! Got: {result}"
            )


class TestWhitespaceBypass:
    """Test that whitespace variations are blocked."""

    @pytest.mark.parametrize("email_with_whitespace,description", [
        (" allowed@example.com", "Leading space"),
        ("allowed@example.com ", "Trailing space"),
        (" allowed@example.com ", "Leading and trailing spaces"),
        ("  allowed@example.com", "Multiple leading spaces"),
        ("allowed@example.com  ", "Multiple trailing spaces"),
        ("allowed @example.com", "Space before @"),
        ("allowed@ example.com", "Space after @"),
        ("allowed@example .com", "Space before .com"),
        ("allowed@example. com", "Space after ."),
        ("\tallowed@example.com", "Leading tab"),
        ("allowed@example.com\t", "Trailing tab"),
        ("\nallowed@example.com", "Leading newline"),
        ("allowed@example.com\n", "Trailing newline"),
        ("allowed@example.com\r\n", "Trailing CRLF"),
    ])
    def test_whitespace_should_be_blocked(
        self, mock_config_with_whitelist, setup_request_context, email_with_whitespace, description
    ):
        """Whitespace-padded emails should NOT bypass the whitelist.

        VULNERABILITY: If this test fails, whitespace can be used to bypass.
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": email_with_whitespace,
                    "subject": "Test",
                    "body": "Test body",
                },
                created_by="test",
            )

            assert result["status"] == "error", (
                f"VULNERABILITY: Whitespace attack ({description}) - "
                f"'{repr(email_with_whitespace)}' was NOT blocked! Got: {result}"
            )


class TestDisplayNameBypass:
    """Test that display name formats are blocked."""

    @pytest.mark.parametrize("email_with_display_name,description", [
        # RFC 5322 display name formats
        ("Attacker <victim@evil.com>", "Display name with malicious address"),
        ('"Attacker" <victim@evil.com>', "Quoted display name"),
        ("allowed@example.com <victim@evil.com>", "Whitelisted as display name"),
        ("<victim@evil.com>", "Angle brackets only"),

        # Trying to hide real recipient
        ("allowed@example.com victim@evil.com", "Two addresses space-separated"),
        ("victim@evil.com, allowed@example.com", "Comma-separated list"),
        ("victim@evil.com; allowed@example.com", "Semicolon-separated list"),

        # Encoded formats
        ("=?UTF-8?B?YWxsb3dlZEBleGFtcGxlLmNvbQ==?= <victim@evil.com>", "Base64 encoded display name"),
    ])
    def test_display_name_formats_should_be_blocked(
        self, mock_config_with_whitelist, setup_request_context, email_with_display_name, description
    ):
        """Display name formats should NOT bypass the whitelist.

        VULNERABILITY: If this test fails, display name injection can bypass.
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": email_with_display_name,
                    "subject": "Test",
                    "body": "Test body",
                },
                created_by="test",
            )

            assert result["status"] == "error", (
                f"VULNERABILITY: Display name attack ({description}) - "
                f"'{email_with_display_name}' was NOT blocked! Got: {result}"
            )


class TestValidWhitelistedEmails:
    """Verify that legitimate whitelisted emails still work."""

    def test_exact_match_should_succeed(self, mock_config_with_whitelist, setup_request_context):
        """Exact match of whitelisted email should succeed."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            with patch("src.agents.tools.task_tools.write_task_atomic"):
                result = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "allowed@example.com",
                        "subject": "Test",
                        "body": "Test body",
                    },
                    created_by="test",
                )

                assert result["status"] == "success", (
                    f"Exact whitelisted email should succeed, got: {result}"
                )

    def test_second_whitelisted_email_should_succeed(
        self, mock_config_with_whitelist, setup_request_context
    ):
        """Second whitelisted email should also succeed."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            with patch("src.agents.tools.task_tools.write_task_atomic"):
                result = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "admin@test.org",
                        "subject": "Test",
                        "body": "Test body",
                    },
                    created_by="test",
                )

                assert result["status"] == "success", (
                    f"Whitelisted email should succeed, got: {result}"
                )


class TestNonWhitelistedEmails:
    """Verify that non-whitelisted emails are blocked."""

    @pytest.mark.parametrize("email", [
        "notallowed@example.com",
        "random@evil.com",
        "attacker@malicious.org",
        "",  # Empty string
    ])
    def test_non_whitelisted_should_be_blocked(
        self, mock_config_with_whitelist, setup_request_context, email
    ):
        """Non-whitelisted emails should be blocked."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config_with_whitelist):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": email,
                    "subject": "Test",
                    "body": "Test body",
                },
                created_by="test",
            )

            assert result["status"] == "error", (
                f"Non-whitelisted email '{email}' should be blocked, got: {result}"
            )


class TestOrchestratorDefenseInDepth:
    """Test the defense-in-depth check in the orchestrator."""

    def test_orchestrator_blocks_case_variation(self, mock_config_with_whitelist):
        """Orchestrator should also block case variations."""
        from src.adk_orchestrator import ADKOrchestrator
        from src.models import AgentTask

        mock_services = MagicMock()

        # Temporarily create orchestrator with mocked config
        with patch("src.adk_orchestrator.FileSessionStore"):
            with patch("src.adk_orchestrator.set_services"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.Runner"):
                        orchestrator = ADKOrchestrator(mock_config_with_whitelist, mock_services)

        # Create an agent task with case variation
        agent_task = AgentTask(
            id="test-123",
            action="send_email",
            params={
                "to_address": "ALLOWED@EXAMPLE.COM",  # Case variation
                "subject": "Test",
                "body": "Test body",
            },
            created_by="test",
            original_sender="attacker@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed", (
            f"VULNERABILITY: Orchestrator defense-in-depth failed! "
            f"Case variation bypassed orchestrator check."
        )
