"""Tests verifying error messages are clear, helpful, and secure.

These tests ensure error messages in tool functions:
1. Clearly explain what went wrong
2. Suggest how to fix the issue (where appropriate)
3. Avoid leaking sensitive information
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.tools.task_tools import create_agent_task


class TestTaskToolsErrorMessages:
    """Tests for error messages in task_tools.py."""

    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create mock config with temp directory."""
        config = MagicMock()
        config.input_dir = temp_dir / "inputs"
        config.input_dir.mkdir(parents=True, exist_ok=True)
        config.allowed_senders = ("allowed@example.com", "admin@example.com")
        return config

    # =========================================================================
    # Error: Invalid action
    # =========================================================================

    def test_invalid_action_error_is_clear(self, mock_config):
        """Error message should clearly state the action is invalid."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="delete_everything",
                params={},
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        # Should clearly state the action is invalid
        assert "Invalid action" in result["message"]
        assert "delete_everything" in result["message"]

    def test_invalid_action_error_suggests_fix(self, mock_config):
        """Error message should list valid actions to help user fix."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="bad_action",
                params={},
                created_by="TestAgent",
            )

        # Should suggest valid options
        assert "send_email" in result["message"]

    def test_invalid_action_error_format(self, mock_config):
        """Error message format should be: 'Invalid action: X. Valid actions: Y'"""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="unknown",
                params={},
                created_by="TestAgent",
            )

        # Verify structured format
        assert "Invalid action: unknown" in result["message"]
        assert "Valid actions:" in result["message"]

    # =========================================================================
    # Error: Missing required parameters
    # =========================================================================

    def test_missing_params_error_is_clear(self, mock_config):
        """Error message should clearly state which params are missing."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={"subject": "Hello"},  # Missing to_address and body
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        # Should mention specific missing params
        assert "to_address" in result["message"]
        assert "body" in result["message"]

    def test_missing_params_error_suggests_fix(self, mock_config):
        """Error message mentions what is needed (by listing missing params)."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={},  # All required params missing
                created_by="TestAgent",
            )

        # Lists all missing params so user knows what to provide
        assert "to_address" in result["message"]
        assert "subject" in result["message"]
        assert "body" in result["message"]

    def test_missing_params_error_context(self, mock_config):
        """Error should mention this is for send_email action."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={},
                created_by="TestAgent",
            )

        # Should provide context about which action failed
        assert "send_email" in result["message"]

    def test_partial_params_only_shows_missing(self, mock_config):
        """When some params provided, only list the missing ones."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={"to_address": "test@example.com", "subject": "Hi"},
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        # Should only mention body (the one that's missing)
        assert "body" in result["message"]
        # Should NOT mention params that were provided
        assert "to_address" not in result["message"] or "Missing" not in result["message"].split("to_address")[0]

    # =========================================================================
    # Error: Recipient not in allowed list
    # =========================================================================

    def test_recipient_not_allowed_error_is_clear(self, mock_config):
        """Error should clearly indicate the recipient restriction."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "random@external.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        assert "not in allowed list" in result["message"]

    def test_recipient_not_allowed_explains_restriction(self, mock_config):
        """Error should explain WHY this restriction exists."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "hacker@evil.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        # Should explain the security rationale
        assert "Cannot send to arbitrary addresses" in result["message"]

    def test_recipient_error_includes_address_attempted(self, mock_config):
        """Error includes the address for debugging purposes.

        Note: This is acceptable in this context because:
        1. The user is already authenticated
        2. They provided the address themselves
        3. It helps them understand which address failed
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "notallowed@domain.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        # The address is included to help user identify which address failed
        assert "notallowed@domain.com" in result["message"]

    # =========================================================================
    # Error: No user context
    # =========================================================================

    def test_no_context_error_is_clear(self, mock_config):
        """Error should clearly state that user context is missing."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch(
                "src.agents.tools.task_tools.get_user_email", return_value=""
            ):
                with patch(
                    "src.agents.tools.task_tools.get_thread_id", return_value=""
                ):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": "Test",
                            "body": "Hello",
                        },
                        created_by="TestAgent",
                    )

        assert result["status"] == "error"
        assert "No user context available" in result["message"]

    def test_no_context_error_action_blocked(self, mock_config):
        """Error should indicate the task cannot be created."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch(
                "src.agents.tools.task_tools.get_user_email", return_value=""
            ):
                with patch(
                    "src.agents.tools.task_tools.get_thread_id", return_value=""
                ):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": "Test",
                            "body": "Hello",
                        },
                        created_by="TestAgent",
                    )

        # Should indicate the consequence
        assert "Cannot create task" in result["message"]

    # =========================================================================
    # Error: File write failure
    # =========================================================================

    def test_write_failure_error_is_clear(self, mock_config):
        """Error should indicate task creation failed."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch(
                "src.agents.tools.task_tools.get_user_email",
                return_value="allowed@example.com",  # Must be in allowed_senders
            ):
                with patch(
                    "src.agents.tools.task_tools.get_thread_id",
                    return_value="thread-123",
                ):
                    with patch(
                        "src.agents.tools.task_tools.write_task_atomic",
                        side_effect=IOError("Disk full"),
                    ):
                        result = create_agent_task(
                            action="send_email",
                            params={
                                "to_address": "admin@example.com",  # Different from sender
                                "subject": "Test",
                                "body": "Hello",
                            },
                            created_by="TestAgent",
                        )

        assert result["status"] == "error"
        assert "Failed to create task" in result["message"]

    def test_write_failure_includes_error_detail(self, mock_config):
        """Error includes the underlying exception for debugging.

        Note: In a production system, you might want to log the full error
        but return a sanitized message. Here, since it's an internal tool,
        including the error is helpful for debugging.
        """
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch(
                "src.agents.tools.task_tools.get_user_email",
                return_value="allowed@example.com",  # Must be in allowed_senders
            ):
                with patch(
                    "src.agents.tools.task_tools.get_thread_id",
                    return_value="thread-123",
                ):
                    with patch(
                        "src.agents.tools.task_tools.write_task_atomic",
                        side_effect=PermissionError("Permission denied: /inputs/task.json"),
                    ):
                        result = create_agent_task(
                            action="send_email",
                            params={
                                "to_address": "admin@example.com",  # Different from sender
                                "subject": "Test",
                                "body": "Hello",
                            },
                            created_by="TestAgent",
                        )

        # Error detail is included for debugging
        assert "Permission denied" in result["message"]

    # =========================================================================
    # Security: Error messages should not leak sensitive info
    # =========================================================================

    def test_error_does_not_leak_allowed_senders_list(self, mock_config):
        """Error should NOT reveal the full list of allowed recipients."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "hacker@evil.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        # Should NOT reveal other allowed addresses (only the attempted one)
        # The message should contain the attempted address but not the allowed list
        assert "hacker@evil.com" in result["message"]  # Shows what user tried
        assert "allowed@example.com" not in result["message"]  # Doesn't leak allowed list
        assert "admin@example.com" not in result["message"]  # Doesn't leak allowed list

    def test_error_does_not_leak_internal_paths(self, mock_config):
        """Errors should not reveal internal file system structure."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="invalid",
                params={},
                created_by="TestAgent",
            )

        # Should not mention internal paths
        assert "/inputs" not in result["message"]
        assert "input_dir" not in result["message"]

    def test_error_does_not_leak_config_details(self, mock_config):
        """Errors should not reveal configuration details."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch(
                "src.agents.tools.task_tools.get_user_email", return_value=""
            ):
                result = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "test@example.com",
                        "subject": "Test",
                        "body": "Hello",
                    },
                    created_by="TestAgent",
                )

        # Should not mention internal implementation details
        assert "request_context" not in result["message"].lower()
        assert "thread_local" not in result["message"].lower()


class TestErrorMessageConsistency:
    """Tests for consistency across error messages."""

    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create mock config with temp directory."""
        config = MagicMock()
        config.input_dir = temp_dir / "inputs"
        config.input_dir.mkdir(parents=True, exist_ok=True)
        config.allowed_senders = ("allowed@example.com",)
        return config

    def test_all_errors_have_status_field(self, mock_config):
        """All error responses should have a status field set to 'error'."""
        error_scenarios = [
            # Invalid action
            {"action": "invalid", "params": {}},
            # Missing params
            {"action": "send_email", "params": {}},
        ]

        for scenario in error_scenarios:
            with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
                result = create_agent_task(
                    action=scenario["action"],
                    params=scenario["params"],
                    created_by="TestAgent",
                )
                assert "status" in result, f"Missing status in response for {scenario}"
                assert result["status"] == "error", f"Status should be 'error' for {scenario}"

    def test_all_errors_have_message_field(self, mock_config):
        """All error responses should have a descriptive message field."""
        error_scenarios = [
            {"action": "invalid", "params": {}},
            {"action": "send_email", "params": {}},
        ]

        for scenario in error_scenarios:
            with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
                result = create_agent_task(
                    action=scenario["action"],
                    params=scenario["params"],
                    created_by="TestAgent",
                )
                assert "message" in result, f"Missing message in response for {scenario}"
                assert len(result["message"]) > 0, f"Message should not be empty for {scenario}"

    def test_error_messages_are_human_readable(self, mock_config):
        """Error messages should be sentences, not codes or IDs."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="bad",
                params={},
                created_by="TestAgent",
            )

        # Should be a readable sentence, not an error code
        message = result["message"]
        assert not message.startswith("ERR_")
        assert not message.startswith("E:")
        # Should contain words
        assert " " in message  # Contains spaces (is a phrase/sentence)
