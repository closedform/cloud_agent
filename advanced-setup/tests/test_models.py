"""Tests for src/models/task.py"""

import pytest

from src.models import Reminder, Task


class TestTask:
    """Tests for the Task model."""

    def test_from_dict_with_required_fields(self):
        """Should create Task from dict with required fields."""
        data = {
            "id": "123",
            "subject": "Test Subject",
            "body": "Test body",
            "sender": "sender@example.com",
            "reply_to": "sender@example.com",
        }
        task = Task.from_dict(data)
        assert task.id == "123"
        assert task.subject == "Test Subject"
        assert task.sender == "sender@example.com"

    def test_from_dict_with_optional_fields(self):
        """Should handle optional fields."""
        data = {
            "id": "123",
            "subject": "Test",
            "body": "Body",
            "sender": "s@e.com",
            "reply_to": "s@e.com",
            "attachments": ["file.pdf"],
            "intent": "schedule",
            "classification": {"key": "value"},
        }
        task = Task.from_dict(data)
        assert task.attachments == ["file.pdf"]
        assert task.intent == "schedule"
        assert task.classification == {"key": "value"}

    def test_from_dict_raises_on_missing_required(self):
        """Should raise ValueError if required fields missing."""
        data = {"id": "123", "subject": "Test"}  # Missing body, sender, reply_to
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(data)
        assert "Missing required fields" in str(exc_info.value)

    def test_to_dict_roundtrip(self):
        """to_dict then from_dict should preserve data."""
        original = Task(
            id="123",
            subject="Test",
            body="Body",
            sender="s@e.com",
            reply_to="r@e.com",
            attachments=["a.txt"],
            intent="research",
            classification={"summary": "test"},
        )
        data = original.to_dict()
        restored = Task.from_dict(data)
        assert restored.id == original.id
        assert restored.subject == original.subject
        assert restored.attachments == original.attachments
        assert restored.intent == original.intent

    def test_create_factory_generates_id(self):
        """Task.create should generate a unique ID."""
        task = Task.create(
            subject="Test",
            body="Body",
            sender="s@e.com",
        )
        assert task.id is not None
        assert len(task.id) > 0

    def test_create_uses_sender_as_reply_to_default(self):
        """Task.create should use sender as reply_to if not provided."""
        task = Task.create(
            subject="Test",
            body="Body",
            sender="sender@example.com",
        )
        assert task.reply_to == "sender@example.com"

    def test_create_uses_explicit_reply_to(self):
        """Task.create should use explicit reply_to if provided."""
        task = Task.create(
            subject="Test",
            body="Body",
            sender="sender@example.com",
            reply_to="reply@example.com",
        )
        assert task.reply_to == "reply@example.com"

    def test_default_attachments_empty_list(self):
        """Default attachments should be empty list."""
        task = Task.create(subject="T", body="B", sender="s@e.com")
        assert task.attachments == []


class TestReminder:
    """Tests for the Reminder model."""

    def test_from_dict_with_required_fields(self):
        """Should create Reminder from dict."""
        data = {
            "id": "rem-123",
            "message": "Call Einstein",
            "datetime": "2026-02-15T09:00:00",
            "reply_to": "user@example.com",
        }
        reminder = Reminder.from_dict(data)
        assert reminder.id == "rem-123"
        assert reminder.message == "Call Einstein"
        assert reminder.datetime == "2026-02-15T09:00:00"

    def test_from_dict_raises_on_missing_required(self):
        """Should raise ValueError if required fields missing."""
        data = {"id": "123", "message": "Test"}  # Missing datetime, reply_to
        with pytest.raises(ValueError) as exc_info:
            Reminder.from_dict(data)
        assert "Missing required fields" in str(exc_info.value)

    def test_to_dict_roundtrip(self):
        """to_dict then from_dict should preserve data."""
        original = Reminder(
            id="rem-123",
            message="Meeting",
            datetime="2026-02-15T09:00:00",
            reply_to="user@example.com",
            created_at="2026-01-27T10:00:00",
        )
        data = original.to_dict()
        restored = Reminder.from_dict(data)
        assert restored.id == original.id
        assert restored.message == original.message
        assert restored.datetime == original.datetime
        assert restored.created_at == original.created_at

    def test_create_factory_generates_id(self):
        """Reminder.create should generate ID if not provided."""
        reminder = Reminder.create(
            message="Test",
            reminder_datetime="2026-02-15T09:00:00",
            reply_to="user@example.com",
        )
        assert reminder.id is not None

    def test_create_uses_task_id(self):
        """Reminder.create should use task_id if provided."""
        reminder = Reminder.create(
            message="Test",
            reminder_datetime="2026-02-15T09:00:00",
            reply_to="user@example.com",
            task_id="task-456",
        )
        assert reminder.id == "task-456"

    def test_create_sets_created_at(self):
        """Reminder.create should set created_at."""
        reminder = Reminder.create(
            message="Test",
            reminder_datetime="2026-02-15T09:00:00",
            reply_to="user@example.com",
        )
        assert reminder.created_at is not None
