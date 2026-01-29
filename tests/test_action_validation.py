"""Tests for action type validation in task_tools.py.

Tests cover:
1. Invalid action types (numbers, None, empty string, very long string)
2. SQL injection in action field
3. Case sensitivity of action names
4. Action with valid name but wrong params structure
"""

from unittest.mock import patch

import pytest


class TestInvalidActionTypes:
    """Tests for invalid action type values."""

    def test_action_with_number_fails(self, test_config):
        """Numeric action type should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action=123,  # Number instead of string
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_action_with_none_fails(self, test_config):
        """None action type should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action=None,  # None instead of string
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_action_with_empty_string_fails(self, test_config):
        """Empty string action type should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="",  # Empty string
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_action_with_very_long_string_fails(self, test_config):
        """Very long action string should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            # 10000 character action string
            long_action = "a" * 10000

            result = create_agent_task(
                action=long_action,
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_action_with_whitespace_only_fails(self, test_config):
        """Whitespace-only action type should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="   ",  # Whitespace only
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]


class TestSQLInjectionInAction:
    """Tests for SQL injection attempts in action field."""

    def test_sql_injection_drop_table_rejected(self, test_config):
        """SQL DROP TABLE injection should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email'; DROP TABLE users;--",
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_sql_injection_union_select_rejected(self, test_config):
        """SQL UNION SELECT injection should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="' UNION SELECT * FROM secrets --",
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_sql_injection_or_1_equals_1_rejected(self, test_config):
        """SQL OR 1=1 injection should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email' OR '1'='1",
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_sql_injection_semicolon_command_rejected(self, test_config):
        """SQL semicolon command chaining should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email; DELETE FROM tasks;",
                params={"to_address": "test@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]


class TestActionCaseSensitivity:
    """Tests for case sensitivity of action names."""

    def test_uppercase_send_email_fails(self, test_config):
        """Uppercase SEND_EMAIL should be rejected (case sensitive)."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="SEND_EMAIL",  # Uppercase
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]
            assert "SEND_EMAIL" in result["message"]

    def test_mixed_case_send_email_fails(self, test_config):
        """Mixed case Send_Email should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="Send_Email",  # Mixed case
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_camel_case_sendEmail_fails(self, test_config):
        """Camel case sendEmail should be rejected."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="sendEmail",  # Camel case
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Invalid action" in result["message"]

    def test_lowercase_send_email_succeeds(self, test_config):
        """Correct lowercase send_email should succeed."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            # Use allowed sender email to pass the security check
            "src.agents.tools.task_tools.get_user_email", return_value="allowed@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",  # Correct lowercase
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "success"
            assert result["action"] == "send_email"


class TestWrongParamsStructure:
    """Tests for valid action name with wrong params structure."""

    def test_send_email_with_missing_to_address(self, test_config):
        """send_email without to_address should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"subject": "Test", "body": "Test"},  # Missing to_address
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Missing required params" in result["message"]
            assert "to_address" in result["message"]

    def test_send_email_with_missing_subject(self, test_config):
        """send_email without subject should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"to_address": "allowed@example.com", "body": "Test"},  # Missing subject
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Missing required params" in result["message"]
            assert "subject" in result["message"]

    def test_send_email_with_missing_body(self, test_config):
        """send_email without body should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"to_address": "allowed@example.com", "subject": "Test"},  # Missing body
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Missing required params" in result["message"]
            assert "body" in result["message"]

    def test_send_email_with_empty_params(self, test_config):
        """send_email with empty params dict should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={},  # Empty params
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Missing required params" in result["message"]

    def test_send_email_with_all_missing_params(self, test_config):
        """send_email with no required params should list all missing."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"icon": "test_icon"},  # Only optional param, no required ones
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "Missing required params" in result["message"]
            # Should mention all three missing required params
            assert "to_address" in result["message"]
            assert "subject" in result["message"]
            assert "body" in result["message"]

    def test_send_email_with_none_values(self, test_config):
        """send_email with None values for required params should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"to_address": None, "subject": None, "body": None},
                created_by="TestAgent",
            )

            # Note: The current implementation checks "if p not in params"
            # so None values pass the presence check but may fail at recipient validation
            # This test documents the current behavior
            assert result["status"] == "error"

    def test_send_email_to_unauthorized_recipient(self, test_config):
        """send_email to unauthorized recipient should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "unauthorized@example.com",  # Not in allowed list
                    "subject": "Test",
                    "body": "Test",
                },
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "not in allowed list" in result["message"]


class TestMissingContext:
    """Tests for missing context (no user email)."""

    def test_action_without_user_context_fails(self, test_config):
        """Valid action without user context should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value=""  # No user email
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "No user context available" in result["message"]

    def test_action_with_none_user_context_fails(self, test_config):
        """Valid action with None user context should fail."""
        with patch(
            "src.agents.tools.task_tools.get_user_email", return_value=None  # None user email
        ), patch(
            "src.agents.tools.task_tools.get_thread_id", return_value="thread-123"
        ), patch(
            "src.agents.tools.task_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.task_tools import create_agent_task

            result = create_agent_task(
                action="send_email",
                params={"to_address": "allowed@example.com", "subject": "Test", "body": "Test"},
                created_by="TestAgent",
            )

            assert result["status"] == "error"
            assert "No user context available" in result["message"]
