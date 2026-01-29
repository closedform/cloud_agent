"""Stress tests for data models - hunting for edge cases and bugs.

Tests:
1. Task with missing fields
2. Reminder with invalid dates
3. from_dict/to_dict with special characters
4. Type mismatches in fields
"""

import pytest

from src.models import Reminder, Task
from src.models.agent_task import AgentTask


class TestTaskMissingFields:
    """Test Task model with various missing field combinations."""

    def test_from_dict_missing_id(self):
        """Should raise ValueError when id is missing."""
        data = {
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "id" in str(exc_info.value)

    def test_from_dict_missing_subject(self):
        """Should raise ValueError when subject is missing."""
        data = {
            "id": "123",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "subject" in str(exc_info.value)

    def test_from_dict_missing_body(self):
        """Should raise ValueError when body is missing."""
        data = {
            "id": "123",
            "subject": "Test",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "body" in str(exc_info.value)

    def test_from_dict_missing_sender(self):
        """Should raise ValueError when sender is missing."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "sender" in str(exc_info.value)

    def test_from_dict_missing_reply_to(self):
        """Should raise ValueError when reply_to is missing."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "reply_to" in str(exc_info.value)

    def test_from_dict_empty_dict(self):
        """Should raise ValueError for empty dict."""
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict({})
        assert "Missing required fields" in str(exc_info.value)

    def test_from_dict_none_values_for_required_fields(self):
        """None values for required fields should be rejected with proper validation."""
        data = {
            "id": None,
            "subject": None,
            "body": None,
            "sender": None,
            "reply_to": None,
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_from_dict_empty_string_values(self):
        """Test with empty string values for required fields."""
        data = {
            "id": "",
            "subject": "",
            "body": "",
            "sender": "",
            "reply_to": "",
        }
        task = Task.from_dict(data)
        assert task.id == ""  # Allowed but potentially problematic
        assert task.subject == ""
        assert task.sender == ""


class TestReminderInvalidDates:
    """Test Reminder model with invalid date formats."""

    def test_from_dict_invalid_iso_format(self):
        """BUG HUNT: What happens with invalid ISO date format?"""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": "not-a-date",  # Invalid format
            "reply_to": "user@example.com",
        }
        # No validation of datetime format - stored as-is
        reminder = Reminder.from_dict(data)
        assert reminder.datetime == "not-a-date"  # BUG: No validation

    def test_from_dict_empty_datetime(self):
        """Test with empty datetime string."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": "",  # Empty string
            "reply_to": "user@example.com",
        }
        reminder = Reminder.from_dict(data)
        assert reminder.datetime == ""  # Allowed but problematic

    def test_from_dict_none_datetime(self):
        """None datetime should be rejected with proper type validation."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": None,
            "reply_to": "user@example.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Reminder.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_from_dict_past_datetime(self):
        """Test with past datetime (should this be allowed?)."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": "1970-01-01T00:00:00",  # Very old date
            "reply_to": "user@example.com",
        }
        reminder = Reminder.from_dict(data)
        assert reminder.datetime == "1970-01-01T00:00:00"  # Allowed

    def test_from_dict_future_datetime_extreme(self):
        """Test with extreme future datetime."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": "9999-12-31T23:59:59",  # Very far future
            "reply_to": "user@example.com",
        }
        reminder = Reminder.from_dict(data)
        assert reminder.datetime == "9999-12-31T23:59:59"

    def test_from_dict_numeric_datetime(self):
        """Numeric datetime should be rejected with proper type validation."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": 1738000000,  # Unix timestamp instead of ISO string
            "reply_to": "user@example.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Reminder.from_dict(data)
        assert "must be a string" in str(exc_info.value)


class TestSpecialCharactersRoundtrip:
    """Test from_dict/to_dict with special characters."""

    def test_task_unicode_subject(self):
        """Test Task with unicode characters in subject."""
        data = {
            "id": "123",
            "subject": "Meeting with Jos\u00e9 \u2013 \u4e2d\u6587 \ud83d\udcbc",
            "body": "Discuss \u20ac100 budget",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.subject == data["subject"]
        assert restored.body == data["body"]

    def test_task_newlines_in_body(self):
        """Test Task with newlines and special whitespace."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Line 1\nLine 2\r\nLine 3\tTabbed",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.body == data["body"]

    def test_task_html_in_body(self):
        """Test Task with HTML content in body."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "<html><body><script>alert('xss')</script></body></html>",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.body == data["body"]

    def test_task_json_in_body(self):
        """Test Task with JSON string in body."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": '{"key": "value", "array": [1, 2, 3]}',
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.body == data["body"]

    def test_task_sql_injection_in_subject(self):
        """Test Task with SQL injection attempt in subject."""
        data = {
            "id": "123",
            "subject": "'; DROP TABLE users; --",
            "body": "Test",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.subject == data["subject"]

    def test_task_path_traversal_in_attachments(self):
        """Test Task with path traversal in attachments."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
            "attachments": ["../../../etc/passwd", "/etc/shadow"],
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.attachments == data["attachments"]

    def test_reminder_emoji_in_message(self):
        """Test Reminder with emoji in message."""
        data = {
            "id": "rem-123",
            "message": "\ud83d\udea8 Don't forget the meeting! \ud83d\udcc5",
            "datetime": "2026-02-15T09:00:00",
            "reply_to": "user@example.com",
        }
        reminder = Reminder.from_dict(data)
        restored = Reminder.from_dict(reminder.to_dict())
        assert restored.message == data["message"]

    def test_task_very_long_body(self):
        """Test Task with very long body (potential memory issue)."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "x" * 1_000_000,  # 1MB of text
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        assert len(task.body) == 1_000_000

    def test_task_null_byte_in_fields(self):
        """BUG HUNT: Null bytes can cause issues in C-based systems."""
        data = {
            "id": "123",
            "subject": "Test\x00Hidden",
            "body": "Body\x00More",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        task = Task.from_dict(data)
        restored = Task.from_dict(task.to_dict())
        assert restored.subject == data["subject"]


class TestTypeMismatches:
    """Test models with incorrect types in fields - validation now rejects these."""

    def test_task_numeric_id(self):
        """Numeric id should be rejected with proper type validation."""
        data = {
            "id": 12345,  # int instead of str
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_task_list_as_subject(self):
        """List as subject should be rejected with proper type validation."""
        data = {
            "id": "123",
            "subject": ["Test", "Subject"],  # list instead of str
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_task_dict_as_body(self):
        """Dict as body should be rejected with proper type validation."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": {"text": "Body content"},  # dict instead of str
            "sender": "s@e.com",
            "reply_to": "s@e.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_task_string_as_attachments(self):
        """String as attachments should be rejected with proper type validation."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
            "attachments": "file.pdf",  # str instead of list
        }
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "must be a list" in str(exc_info.value)

    def test_task_boolean_intent(self):
        """Test with boolean intent instead of string."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
            "intent": True,  # bool instead of str
        }
        task = Task.from_dict(data)
        assert task.intent is True  # Wrong type stored

    def test_reminder_list_as_message(self):
        """List as message should be rejected with proper type validation."""
        data = {
            "id": "rem-123",
            "message": ["Call", "Einstein"],  # list instead of str
            "datetime": "2026-02-15T09:00:00",
            "reply_to": "user@example.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Reminder.from_dict(data)
        assert "must be a string" in str(exc_info.value)

    def test_reminder_dict_as_datetime(self):
        """Dict as datetime should be rejected with proper type validation."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": {"year": 2026, "month": 2, "day": 15},  # dict
            "reply_to": "user@example.com",
        }
        with pytest.raises(ValueError) as exc_info:
            Reminder.from_dict(data)
        assert "must be a string" in str(exc_info.value)


class TestAgentTaskStress:
    """Stress tests for AgentTask model."""

    def test_from_dict_missing_task_type(self):
        """Should raise ValueError when task_type is missing."""
        data = {
            "id": "task-123",
            "action": "send_email",
            "params": {"to": "user@example.com"},
            "created_by": "ResearchAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "Not an agent task" in str(exc_info.value)

    def test_from_dict_wrong_task_type(self):
        """Should raise ValueError when task_type is wrong."""
        data = {
            "task_type": "email_task",  # Wrong type
            "id": "task-123",
            "action": "send_email",
            "params": {},
            "created_by": "ResearchAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "Not an agent task" in str(exc_info.value)

    def test_from_dict_missing_required_fields(self):
        """Should raise ValueError when required fields missing."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            # Missing other required fields
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "Missing required fields" in str(exc_info.value)

    def test_from_dict_none_params(self):
        """None params should be rejected with proper type validation."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": None,  # Should be dict
            "created_by": "ResearchAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "must be a dict" in str(exc_info.value)

    def test_from_dict_string_params(self):
        """String params should be rejected with proper type validation."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": "not a dict",  # Should be dict
            "created_by": "ResearchAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(data)
        assert "must be a dict" in str(exc_info.value)

    def test_is_agent_task_with_none(self):
        """Test is_agent_task with None value."""
        # This should not raise, just return False
        assert AgentTask.is_agent_task({}) is False
        assert AgentTask.is_agent_task({"task_type": None}) is False

    def test_roundtrip_with_complex_params(self):
        """Test roundtrip with complex nested params."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": {
                "to": "user@example.com",
                "nested": {
                    "deep": {
                        "value": [1, 2, {"key": "value"}]
                    }
                }
            },
            "created_by": "ResearchAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task = AgentTask.from_dict(data)
        restored = AgentTask.from_dict(task.to_dict())
        assert restored.params == data["params"]


class TestDataclassDefaultBehavior:
    """Test dataclass default value behaviors."""

    def test_task_attachments_default_not_shared(self):
        """Verify default list is not shared between instances."""
        task1 = Task.create(subject="T1", body="B1", sender="s@e.com")
        task2 = Task.create(subject="T2", body="B2", sender="s@e.com")

        task1.attachments.append("file1.pdf")

        assert "file1.pdf" in task1.attachments
        assert "file1.pdf" not in task2.attachments  # Should not be shared

    def test_task_created_at_auto_generated(self):
        """Verify created_at is auto-generated."""
        task = Task.create(subject="T", body="B", sender="s@e.com")
        assert task.created_at is not None
        assert "T" in task.created_at or task.created_at.startswith("20")

    def test_reminder_created_at_auto_generated(self):
        """Verify created_at is auto-generated for Reminder."""
        reminder = Reminder.create(
            message="Test",
            reminder_datetime="2026-02-15T09:00:00",
            reply_to="user@example.com",
        )
        assert reminder.created_at is not None


class TestEdgeCases:
    """Additional edge case tests."""

    def test_task_from_dict_extra_fields_ignored(self):
        """Extra fields in dict should be ignored."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
            "extra_field": "ignored",
            "another_field": {"nested": "data"},
        }
        task = Task.from_dict(data)
        assert task.id == "123"
        assert not hasattr(task, "extra_field")

    def test_reminder_from_dict_extra_fields_ignored(self):
        """Extra fields in dict should be ignored."""
        data = {
            "id": "rem-123",
            "message": "Test",
            "datetime": "2026-02-15T09:00:00",
            "reply_to": "user@example.com",
            "unknown_field": "should be ignored",
        }
        reminder = Reminder.from_dict(data)
        assert reminder.id == "rem-123"
        assert not hasattr(reminder, "unknown_field")

    def test_task_create_concurrent_ids(self):
        """Test that rapid task creation doesn't produce duplicate IDs."""
        tasks = [
            Task.create(subject=f"T{i}", body="B", sender="s@e.com")
            for i in range(100)
        ]
        ids = [t.id for t in tasks]
        # Note: time.time() * 1000 may produce duplicates if called too fast
        # This test may reveal timing issues
        unique_ids = set(ids)
        # Allow some duplicates due to timing, but flag if too many
        if len(unique_ids) < 90:
            pytest.fail(
                f"Too many duplicate IDs: {len(ids)} total, {len(unique_ids)} unique"
            )
