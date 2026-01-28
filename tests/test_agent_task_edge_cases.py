"""Edge case tests for create_agent_task."""

import pytest
from unittest.mock import patch

from src.agents.tools.task_tools import create_agent_task
from src.agents.tools._context import set_request_context, clear_request_context


@pytest.fixture(autouse=True)
def setup_context(test_config):
    """Set up request context for each test."""
    with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
        # Set valid user context
        set_request_context(
            user_email="allowed@example.com",
            thread_id="test-thread-123",
            reply_to="allowed@example.com",
            body="Test body",
        )
        yield
        clear_request_context()


class TestEmptyStringParams:
    """Test behavior when params contain empty strings."""

    def test_empty_to_address(self, test_config, temp_dir):
        """Test with empty string for to_address."""
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "",  # Empty string
                    "subject": "Test Subject",
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # Should fail validation - empty string caught by empty value check
        assert result["status"] == "error"
        assert "Empty or invalid" in result["message"]

    def test_empty_subject(self, test_config, temp_dir):
        """Test with empty string for subject.

        BUG FOUND: Empty subject string passes validation and creates a task.
        Expected: Should fail with validation error for empty subject.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "",  # Empty string
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # BUG: Empty string passes validation but creates invalid email task
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: Empty subject accepted! Result: {result}"

        # Current behavior: succeeds (this is a bug)
        # Expected behavior: should fail with validation error

    def test_empty_body(self, test_config, temp_dir):
        """Test with empty string for body.

        BUG FOUND: Empty body string passes validation and creates a task.
        Expected: Should fail with validation error for empty body.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test Subject",
                    "body": "",  # Empty string
                },
                created_by="TestAgent",
            )

        # BUG: Empty string passes validation but creates invalid email task
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: Empty body accepted! Result: {result}"

        # Current behavior: succeeds (this is a bug)
        # Expected behavior: should fail with validation error

    def test_all_empty_strings(self, test_config, temp_dir):
        """Test with all params as empty strings."""
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "",
                    "subject": "",
                    "body": "",
                },
                created_by="TestAgent",
            )

        # Should fail - empty to_address is not in allowed list
        assert result["status"] == "error"


class TestNoneValues:
    """Test behavior when params contain None values."""

    def test_none_to_address(self, test_config, temp_dir):
        """Test with None for to_address."""
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": None,  # None value
                    "subject": "Test Subject",
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # BUG: None passes the "in params" check but fails allowed_senders check
        # Should get a clearer error message about None not being valid
        print(f"Result for None to_address: {result}")
        assert result["status"] == "error"

    def test_none_subject(self, test_config, temp_dir):
        """Test with None for subject.

        BUG FOUND: None subject passes validation and creates a task.
        Expected: Should fail with validation error for None subject.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": None,  # None value
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # BUG: None passes validation because key exists
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: None subject accepted! Result: {result}"

        # Current behavior: succeeds (this is a bug)
        # Expected behavior: should fail with validation error

    def test_none_body(self, test_config, temp_dir):
        """Test with None for body.

        BUG FOUND: None body passes validation and creates a task.
        Expected: Should fail with validation error for None body.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test Subject",
                    "body": None,  # None value
                },
                created_by="TestAgent",
            )

        # BUG: None passes validation because key exists
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: None body accepted! Result: {result}"

        # Current behavior: succeeds (this is a bug)
        # Expected behavior: should fail with validation error

    def test_all_none_values(self, test_config, temp_dir):
        """Test with all params as None."""
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": None,
                    "subject": None,
                    "body": None,
                },
                created_by="TestAgent",
            )

        # Should fail - None is not in allowed list
        assert result["status"] == "error"


class TestWhitespaceOnlyParams:
    """Test behavior when params contain only whitespace."""

    def test_whitespace_subject(self, test_config, temp_dir):
        """Test with whitespace-only subject.

        BUG FOUND: Whitespace-only subject passes validation and creates a task.
        Expected: Should fail with validation error for whitespace-only subject.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "   ",  # Whitespace only
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # BUG: Whitespace-only subject passes validation
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: Whitespace subject accepted! Result: {result}"

    def test_whitespace_body(self, test_config, temp_dir):
        """Test with whitespace-only body.

        BUG FOUND: Whitespace-only body passes validation and creates a task.
        Expected: Should fail with validation error for whitespace-only body.
        """
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test Subject",
                    "body": "\n\t  ",  # Whitespace only
                },
                created_by="TestAgent",
            )

        # BUG: Whitespace-only body passes validation
        # This assertion demonstrates the bug - it SHOULD be "error" but it's "success"
        assert result["status"] == "error", f"BUG: Whitespace body accepted! Result: {result}"


class TestMissingContext:
    """Test behavior when request context is missing."""

    def test_no_user_context(self, test_config, temp_dir):
        """Test when user context is cleared."""
        # Create input dir
        (temp_dir / "inputs").mkdir(parents=True, exist_ok=True)

        # Clear the context that was set in setup
        clear_request_context()

        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test Subject",
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

        # Should fail - no user context
        assert result["status"] == "error"
        assert "No user context available" in result["message"]
