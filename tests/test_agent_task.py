"""Tests for agent task creation and execution."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import AgentTask
from src.agents.tools.task_tools import create_agent_task


class TestAgentTaskModel:
    """Tests for the AgentTask model."""

    def test_from_dict_with_required_fields(self):
        """Should create AgentTask from dict with required fields."""
        data = {
            "task_type": "agent_task",
            "id": "abc123",
            "action": "send_email",
            "params": {"to_address": "test@example.com", "subject": "Hi", "body": "Hello"},
            "created_by": "RouterAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task = AgentTask.from_dict(data)
        assert task.id == "abc123"
        assert task.action == "send_email"
        assert task.params["to_address"] == "test@example.com"
        assert task.created_by == "RouterAgent"
        assert task.task_type == "agent_task"

    def test_from_dict_raises_on_wrong_type(self):
        """Should raise ValueError if task_type is not agent_task."""
        data = {
            "id": "123",
            "action": "send_email",
            "params": {},
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "Not an agent task" in str(exc_info.value)

    def test_from_dict_raises_on_missing_required(self):
        """Should raise ValueError if required fields missing."""
        data = {
            "task_type": "agent_task",
            "id": "123",
            "action": "send_email",
        }  # Missing params, created_by, original_sender, original_thread_id
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "Missing required fields" in str(exc_info.value)

    def test_to_dict_roundtrip(self):
        """to_dict then from_dict should preserve data."""
        original = AgentTask(
            id="abc123",
            action="send_email",
            params={"to_address": "test@example.com", "subject": "Hi", "body": "Hello"},
            created_by="RouterAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )
        data = original.to_dict()
        restored = AgentTask.from_dict(data)
        assert restored.id == original.id
        assert restored.action == original.action
        assert restored.params == original.params
        assert restored.created_by == original.created_by

    def test_is_agent_task_returns_true(self):
        """is_agent_task should return True for agent tasks."""
        data = {"task_type": "agent_task", "id": "123"}
        assert AgentTask.is_agent_task(data) is True

    def test_is_agent_task_returns_false_for_email_task(self):
        """is_agent_task should return False for regular email tasks."""
        data = {"id": "123", "subject": "Test", "body": "Hello"}
        assert AgentTask.is_agent_task(data) is False


class TestCreateAgentTask:
    """Tests for the create_agent_task tool function."""

    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create mock config with temp directory."""
        config = MagicMock()
        config.input_dir = temp_dir / "inputs"
        config.input_dir.mkdir(parents=True, exist_ok=True)
        config.allowed_senders = ("allowed@example.com", "other@example.com")
        return config

    def test_invalid_action_returns_error(self, mock_config):
        """Should return error for invalid action."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="invalid_action",
                params={},
                created_by="TestAgent",
            )
        assert result["status"] == "error"
        assert "Invalid action" in result["message"]

    def test_send_email_missing_params_returns_error(self, mock_config):
        """Should return error if send_email missing required params."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={"subject": "Hi"},  # Missing to_address and body
                created_by="TestAgent",
            )
        assert result["status"] == "error"
        assert "Missing required params" in result["message"]

    def test_send_email_to_non_allowed_recipient_returns_error(self, mock_config):
        """Should return error if recipient not in allowed list."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch("src.agents.tools.task_tools.get_user_email", return_value="user@example.com"):
                with patch("src.agents.tools.task_tools.get_thread_id", return_value="thread-123"):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "notallowed@example.com",
                            "subject": "Hi",
                            "body": "Hello",
                        },
                        created_by="TestAgent",
                    )
        assert result["status"] == "error"
        assert "not in allowed list" in result["message"]

    def test_send_email_creates_task_file(self, mock_config):
        """Should create task file for valid send_email action."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch("src.agents.tools.task_tools.get_user_email", return_value="user@example.com"):
                with patch("src.agents.tools.task_tools.get_thread_id", return_value="thread-123"):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": "Welcome",
                            "body": "Welcome to the system!",
                        },
                        created_by="RouterAgent",
                    )

        assert result["status"] == "success"
        assert "task_id" in result
        assert result["action"] == "send_email"

        # Verify task file was created
        task_files = list(mock_config.input_dir.glob("task_*.json"))
        assert len(task_files) == 1

        # Verify task file content
        with open(task_files[0]) as f:
            task_data = json.load(f)

        assert task_data["task_type"] == "agent_task"
        assert task_data["action"] == "send_email"
        assert task_data["params"]["to_address"] == "allowed@example.com"
        assert task_data["created_by"] == "RouterAgent"
        assert task_data["original_sender"] == "user@example.com"
        assert task_data["original_thread_id"] == "thread-123"

    def test_no_user_context_returns_error(self, mock_config):
        """Should return error if no user context available."""
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch("src.agents.tools.task_tools.get_user_email", return_value=""):
                with patch("src.agents.tools.task_tools.get_thread_id", return_value=""):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": "Hi",
                            "body": "Hello",
                        },
                        created_by="TestAgent",
                    )
        assert result["status"] == "error"
        assert "No user context" in result["message"]
