"""Tests for src/agents/tools/personal_data_tools.py"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.reminders import _load_reminders, _reminders_lock


class TestTodoReminderScheduling:
    """Tests for todo reminder scheduling."""

    def test_todo_with_reminder_creates_reminder(self, test_config):
        """Todo with due_date and reminder_days_before should schedule a reminder."""
        # Calculate future due date
        due_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

        # Mock the request context
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            result = add_todo_item(
                text="Test todo with reminder",
                due_date=due_date,
                reminder_days_before=3,
            )

            assert result["status"] == "success"
            assert "reminder" in result

            # Check reminder was actually created
            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 1
            assert "Test todo with reminder" in reminders[0]["message"]

    def test_todo_without_due_date_no_reminder(self, test_config):
        """Todo without due_date should not create a reminder."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            result = add_todo_item(text="Test todo without reminder")

            assert result["status"] == "success"
            assert "reminder" not in result

            # Check no reminder was created
            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 0

    def test_todo_past_due_date_no_reminder(self, test_config):
        """Todo with past due date should not create a reminder."""
        # Past due date
        due_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            result = add_todo_item(
                text="Test past todo",
                due_date=due_date,
                reminder_days_before=3,
            )

            assert result["status"] == "success"
            # Reminder should not be scheduled for past dates
            assert "reminder" not in result

            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 0

    def test_reminder_time_is_9am(self, test_config):
        """Reminder should be scheduled for 9 AM on the reminder day."""
        due_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            add_todo_item(
                text="Test reminder time",
                due_date=due_date,
                reminder_days_before=3,
            )

            with _reminders_lock:
                reminders = _load_reminders(test_config)

            assert len(reminders) == 1
            reminder_time = datetime.fromisoformat(reminders[0]["datetime"])
            assert reminder_time.hour == 9
            assert reminder_time.minute == 0

