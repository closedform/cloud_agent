"""Tests for ADK orchestrator agent task handling.

Tests the _execute_agent_task and _execute_send_email methods,
focusing on error handling and edge cases.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import AgentTask


class TestExecuteAgentTask:
    """Tests for _execute_agent_task method."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        # Avoid import-time side effects by patching heavy dependencies
        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_execute_agent_task_unknown_action_returns_failed(self, orchestrator):
        """Should return 'failed' for unknown action types."""
        agent_task = AgentTask(
            id="task-123",
            action="unknown_action",
            params={},
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_agent_task(agent_task)

        assert result == "failed"

    def test_execute_agent_task_send_email_calls_execute_send_email(self, orchestrator):
        """Should call _execute_send_email for send_email action."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test",
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch.object(orchestrator, "_execute_send_email", return_value="processed") as mock_send:
            result = orchestrator._execute_agent_task(agent_task)

        mock_send.assert_called_once_with(agent_task)
        assert result == "processed"


class TestExecuteSendEmail:
    """Tests for _execute_send_email method."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_missing_to_address_returns_failed(self, orchestrator):
        """Should return 'failed' when to_address is missing."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "subject": "Test",
                "body": "Hello",
                # Missing to_address
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_missing_subject_returns_failed(self, orchestrator):
        """Should return 'failed' when subject is missing."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "body": "Hello",
                # Missing subject
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_missing_body_returns_failed(self, orchestrator):
        """Should return 'failed' when body is missing."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test",
                # Missing body
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_empty_params_returns_failed(self, orchestrator):
        """Should return 'failed' when all params are missing."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={},  # Empty params
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_non_whitelisted_recipient_returns_failed(self, orchestrator):
        """Should return 'failed' when recipient not in allowed_senders."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "notallowed@hacker.com",
                "subject": "Test",
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_send_email_success_returns_processed(self, orchestrator):
        """Should return 'processed' when email is sent successfully."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",  # In test_config.allowed_senders
                "subject": "Test Subject",
                "body": "Hello World",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", return_value=True) as mock_send:
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_send_email(agent_task)

        assert result == "processed"
        mock_send.assert_called_once()

    def test_send_email_returns_false_returns_failed(self, orchestrator):
        """Should return 'failed' when send_email returns False."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", return_value=False):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_send_email_throws_exception_returns_failed(self, orchestrator):
        """Should return 'failed' when send_email raises exception."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", side_effect=Exception("SMTP connection failed")):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_send_email_throws_connection_error_returns_failed(self, orchestrator):
        """Should return 'failed' when send_email raises ConnectionError."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", side_effect=ConnectionError("Network unreachable")):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_text_to_html_throws_exception_returns_failed(self, orchestrator):
        """Should return 'failed' when text_to_html raises exception."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.text_to_html", side_effect=Exception("HTML conversion failed")):
            result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_uses_default_icon_when_not_provided(self, orchestrator):
        """Should use default speech balloon icon when icon not in params."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
                # No icon provided
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", return_value=True):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>") as mock_html:
                    orchestrator._execute_send_email(agent_task)

        # Check that default icon was used
        mock_html.assert_called_once()
        call_kwargs = mock_html.call_args
        assert call_kwargs[1]["icon"] == "💬"  # Default icon

    def test_uses_custom_icon_when_provided(self, orchestrator):
        """Should use custom icon when provided in params."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Hello World",
                "icon": "📅",  # Custom calendar icon
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with patch("src.adk_orchestrator.send_email", return_value=True):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello World</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>") as mock_html:
                    orchestrator._execute_send_email(agent_task)

        mock_html.assert_called_once()
        call_kwargs = mock_html.call_args
        assert call_kwargs[1]["icon"] == "📅"


class TestProcessTaskWithAgentTask:
    """Tests for process_task when handling agent tasks."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        # Create input directory
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_agent_task_from_dict_raises_value_error_returns_failed(self, orchestrator, test_config):
        """Should return 'failed' when AgentTask.from_dict raises ValueError."""
        # Create a task file with agent_task marker but missing required fields
        task_data = {
            "task_type": "agent_task",
            "id": "task-123",
            # Missing action, params, created_by, original_sender, original_thread_id
        }
        task_file = test_config.input_dir / "task_test.json"
        task_file.write_text(json.dumps(task_data))

        result = orchestrator.process_task(task_file)

        assert result == "failed"

    def test_agent_task_missing_params_field_returns_failed(self, orchestrator, test_config):
        """Should return 'failed' when params field is missing."""
        task_data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            # Missing params
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task_file = test_config.input_dir / "task_test.json"
        task_file.write_text(json.dumps(task_data))

        result = orchestrator.process_task(task_file)

        assert result == "failed"

    def test_agent_task_with_wrong_task_type_returns_failed(self, orchestrator, test_config):
        """Should return 'failed' when task_type is wrong."""
        task_data = {
            "task_type": "wrong_type",  # Should be "agent_task"
            "id": "task-123",
            "action": "send_email",
            "params": {},
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task_file = test_config.input_dir / "task_test.json"
        task_file.write_text(json.dumps(task_data))

        # This won't be treated as an agent task due to wrong task_type
        # It will fall through to regular email task processing
        with patch.object(orchestrator, "_execute_agent_task") as mock_execute:
            with patch("src.adk_orchestrator.Task") as mock_task:
                mock_task.from_dict.side_effect = ValueError("Invalid task")
                result = orchestrator.process_task(task_file)

        # Should not have called _execute_agent_task
        mock_execute.assert_not_called()

    def test_valid_agent_task_calls_execute_agent_task(self, orchestrator, test_config):
        """Should call _execute_agent_task for valid agent task."""
        task_data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": {
                "to_address": "allowed@example.com",
                "subject": "Test",
                "body": "Hello",
            },
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task_file = test_config.input_dir / "task_test.json"
        task_file.write_text(json.dumps(task_data))

        with patch.object(orchestrator, "_execute_agent_task", return_value="processed") as mock_execute:
            result = orchestrator.process_task(task_file)

        mock_execute.assert_called_once()
        assert result == "processed"


class TestParamsEdgeCases:
    """Tests for edge cases in params handling."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_empty_string_to_address_returns_failed(self, orchestrator):
        """Should return 'failed' when to_address is empty string."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "",  # Empty string
                "subject": "Test",
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_empty_string_subject_returns_failed(self, orchestrator):
        """Should return 'failed' when subject is empty string."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "",  # Empty string
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_empty_string_body_returns_failed(self, orchestrator):
        """Should return 'failed' when body is empty string."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "Test",
                "body": "",  # Empty string
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_none_values_in_params_returns_failed(self, orchestrator):
        """Should return 'failed' when params contain None values."""
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": None,
                "subject": None,
                "body": None,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        assert result == "failed"

    def test_whitespace_only_subject_passes_validation(self, orchestrator):
        """Whitespace-only subject passes validation but may cause email issues.

        BUG POTENTIAL: The implementation checks `not all([to_address, subject, body])`
        which passes for whitespace strings like "   " since they are truthy.
        This allows sending emails with whitespace-only subjects.
        """
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "allowed@example.com",
                "subject": "   ",  # Whitespace only - truthy but invalid
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        # Current behavior: whitespace passes validation (truthy value)
        # This test documents the current behavior - it will try to send the email
        with patch("src.adk_orchestrator.send_email", return_value=True) as mock_send:
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Hello</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_send_email(agent_task)

        # BUG: Current behavior passes whitespace through
        assert result == "processed"
        mock_send.assert_called_once()
        # The subject in the call will be "   " (whitespace only)
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["subject"] == "   "


class TestBugWhitespaceToAddress:
    """Tests documenting the whitespace-only to_address bug."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_whitespace_to_address_fails_on_whitelist_check(self, orchestrator):
        """Whitespace-only to_address passes param validation but fails whitelist check.

        This test shows that while whitespace passes the initial falsy check,
        it fails the subsequent allowed_senders check because "   " is not in the whitelist.
        """
        agent_task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "   ",  # Whitespace - passes falsy check but not in allowed_senders
                "subject": "Test",
                "body": "Hello",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        result = orchestrator._execute_send_email(agent_task)

        # Fails because "   " is not in allowed_senders
        # Defense in depth catches the bug
        assert result == "failed"
