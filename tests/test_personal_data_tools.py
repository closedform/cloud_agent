"""Tests for src/agents/tools/personal_data_tools.py"""

import json
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


class TestInputValidation:
    """Tests for input validation in personal data tools."""

    def test_add_item_empty_list_name(self, test_config):
        """Adding item with empty list name should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_item_to_list

            result = add_item_to_list(list_name="", item="test item")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_item_empty_item(self, test_config):
        """Adding empty item should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_item_to_list

            result = add_item_to_list(list_name="movies", item="")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_item_whitespace_only_stripped(self, test_config):
        """Whitespace-only inputs should be treated as empty."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_item_to_list

            result = add_item_to_list(list_name="   ", item="test")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_todo_empty_text(self, test_config):
        """Adding todo with empty text should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            result = add_todo_item(text="")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_todo_negative_reminder_days(self, test_config):
        """Adding todo with negative reminder days should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import add_todo_item

            result = add_todo_item(
                text="Test todo",
                due_date="2026-03-01",
                reminder_days_before=-1,
            )
            assert result["status"] == "error"
            assert "non-negative" in result["message"].lower()

    def test_add_todo_zero_reminder_days_valid(self, test_config):
        """Adding todo with 0 reminder days (reminder on due date) should work."""
        # Calculate a future date
        future_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

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
                text="Test todo with zero days",
                due_date=future_date,
                reminder_days_before=0,
            )
            assert result["status"] == "success"
            # Reminder should be scheduled for the due date at 9 AM
            assert "reminder" in result

    def test_complete_todo_empty_text(self, test_config):
        """Completing todo with empty text should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import complete_todo_item

            result = complete_todo_item(text_or_id="")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_remove_item_empty_inputs(self, test_config):
        """Removing item with empty inputs should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import remove_item_from_list

            result = remove_item_from_list(list_name="", item="test")
            assert result["status"] == "error"

            result = remove_item_from_list(list_name="movies", item="")
            assert result["status"] == "error"

    def test_get_list_items_empty_name(self, test_config):
        """Getting items from list with empty name should return error."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import get_list_items

            result = get_list_items(list_name="")
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()


class TestNewTools:
    """Tests for delete_todo_item and clear_list tools."""

    def test_delete_todo_by_text(self, test_config):
        """Should delete a todo by matching text."""
        # First create a todo
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

            from src.agents.tools.personal_data_tools import (
                add_todo_item,
                delete_todo_item,
                get_user_todos,
            )

            # Create a todo
            add_todo_item(text="Buy groceries")

            # Verify it exists
            todos_before = get_user_todos()
            assert todos_before["count"] == 1

            # Delete it
            result = delete_todo_item(text_or_id="groceries")
            assert result["status"] == "success"
            assert "Buy groceries" in result["message"]

            # Verify it's gone
            todos_after = get_user_todos(include_completed=True)
            assert todos_after["count"] == 0

    def test_delete_todo_by_id(self, test_config):
        """Should delete a todo by ID."""
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

            from src.agents.tools.personal_data_tools import (
                add_todo_item,
                delete_todo_item,
                get_user_todos,
            )

            # Create a todo
            result = add_todo_item(text="Test todo to delete")
            todo_id = result["todo"]["id"]

            # Delete by ID
            result = delete_todo_item(text_or_id=todo_id)
            assert result["status"] == "success"

    def test_delete_todo_not_found(self, test_config):
        """Should return error for non-existent todo."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import delete_todo_item

            result = delete_todo_item(text_or_id="nonexistent todo")
            assert result["status"] == "error"

    def test_delete_todo_empty_input(self, test_config):
        """Should return error for empty input."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import delete_todo_item

            result = delete_todo_item(text_or_id="")
            assert result["status"] == "error"

    def test_clear_list(self, test_config):
        """Should clear all items from a list."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import (
                add_item_to_list,
                clear_list,
                get_user_lists,
            )

            # Add some items
            add_item_to_list(list_name="test_list", item="item1")
            add_item_to_list(list_name="test_list", item="item2")

            # Clear the list
            result = clear_list(list_name="test_list")
            assert result["status"] == "success"
            assert result["items_removed"] == 2

            # Verify list is gone
            lists = get_user_lists()
            list_names = [l["name"] for l in lists.get("lists", [])]
            assert "test_list" not in list_names

    def test_clear_list_not_found(self, test_config):
        """Should return error for non-existent list."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import clear_list

            result = clear_list(list_name="nonexistent_list")
            assert result["status"] == "error"

    def test_clear_list_empty_name(self, test_config):
        """Should return error for empty list name."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import clear_list

            result = clear_list(list_name="")
            assert result["status"] == "error"


class TestMissingUserEmail:
    """Tests for handling missing user email context."""

    def test_all_tools_require_user_email(self, test_config):
        """All tools should return error when user email is not available."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value=None,
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.personal_data_tools import (
                add_item_to_list,
                add_todo_item,
                clear_list,
                complete_todo_item,
                delete_todo_item,
                get_list_items,
                get_user_lists,
                get_user_todos,
                remove_item_from_list,
            )

            # Test each tool
            assert get_user_lists()["status"] == "error"
            assert get_list_items("movies")["status"] == "error"
            assert add_item_to_list("movies", "test")["status"] == "error"
            assert remove_item_from_list("movies", "test")["status"] == "error"
            assert clear_list("movies")["status"] == "error"
            assert get_user_todos()["status"] == "error"
            assert add_todo_item("test")["status"] == "error"
            assert complete_todo_item("test")["status"] == "error"
            assert delete_todo_item("test")["status"] == "error"

