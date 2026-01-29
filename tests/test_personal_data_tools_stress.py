"""Stress tests for personal_data_tools: Edge cases and data isolation.

Tests for:
1. Todo with past due dates
2. Duplicate list items
3. Empty list names
4. Cross-user data isolation
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.agents.tools._context import set_request_context, clear_request_context
from src.agents.tools.personal_data_tools import (
    add_item_to_list,
    add_todo_item,
    complete_todo_item,
    get_list_items,
    get_user_lists,
    get_user_todos,
    remove_item_from_list,
)
from src.reminders import _load_reminders, _reminders_lock
from src.user_data import load_user_data


class TestPastDueDates:
    """Tests for todos with past due dates."""

    def test_add_todo_with_past_due_date_succeeds(self, test_config):
        """Adding a todo with a past due date should succeed (no validation)."""
        past_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = add_todo_item(
                text="Overdue task from last month",
                due_date=past_date,
            )

            # BUG HUNT: Does it accept past due dates without warning?
            assert result["status"] == "success"
            assert result["todo"]["due_date"] == past_date
            # No warning or indication that the date is in the past

    def test_add_todo_with_past_due_date_and_reminder(self, test_config):
        """Adding todo with past due date + reminder should handle gracefully."""
        past_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = add_todo_item(
                text="Overdue task with reminder",
                due_date=past_date,
                reminder_days_before=3,
            )

            # Todo is still created
            assert result["status"] == "success"
            # Reminder is skipped (correctly) for past dates
            assert "reminder" not in result
            # Check there's a note about it
            assert "reminder_note" in result

            # Verify no reminder was scheduled
            with _reminders_lock:
                reminders = _load_reminders(test_config)
            assert len(reminders) == 0

    def test_todo_due_today_with_reminder_same_day(self, test_config):
        """Todo due today with 0 days reminder might have edge case issues."""
        today = datetime.now().strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = add_todo_item(
                text="Due today task",
                due_date=today,
                reminder_days_before=0,  # Remind on the same day
            )

            # BUG HUNT: Reminder would be for 9am today - may or may not be in past
            # depending on current time
            assert result["status"] == "success"

    def test_todo_invalid_date_format(self, test_config):
        """Todo with invalid date format should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Invalid date formats are now properly rejected
            invalid_dates = [
                "2026/01/15",  # Wrong separator
                "01-15-2026",  # Wrong order
                "January 15, 2026",  # Natural language
                "not-a-date",  # Garbage
            ]

            for invalid_date in invalid_dates:
                result = add_todo_item(
                    text=f"Task with invalid date: {invalid_date}",
                    due_date=invalid_date,
                    reminder_days_before=1,
                )

                # Invalid date formats are now properly rejected
                assert result["status"] == "error"
                assert "invalid" in result["message"].lower() or "format" in result["message"].lower()

    def test_todo_empty_date_string(self, test_config):
        """Todo with empty string date should be rejected (not silently ignored)."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = add_todo_item(
                text="Task with empty date",
                due_date="",  # Empty string
                reminder_days_before=1,
            )

            # Empty string is now validated and rejected
            assert result["status"] == "error"
            assert "invalid" in result["message"].lower() or "format" in result["message"].lower()


class TestDuplicateListItems:
    """Tests for duplicate items in lists."""

    def test_add_duplicate_items_allows_duplicates(self, test_config):
        """Adding the same item twice should... allow duplicates? Or not?"""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # Add same item twice
            result1 = add_item_to_list("groceries", "milk")
            result2 = add_item_to_list("groceries", "milk")

            # BUG: Duplicates are allowed
            assert result1["total_count"] == 1
            assert result2["total_count"] == 2  # Duplicate added

            # Verify both are in the list
            items_result = get_list_items("groceries")
            assert items_result["items"] == ["milk", "milk"]

    def test_add_case_variant_duplicates(self, test_config):
        """Adding items with different case should... be considered duplicates?"""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("groceries", "Milk")
            add_item_to_list("groceries", "milk")
            add_item_to_list("groceries", "MILK")

            items_result = get_list_items("groceries")
            # BUG: All three case variants are stored as separate items
            assert items_result["count"] == 3
            assert items_result["items"] == ["Milk", "milk", "MILK"]

    def test_remove_duplicate_only_removes_first(self, test_config):
        """Removing from list with duplicates should remove only the first match."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # Add three items
            add_item_to_list("groceries", "milk")
            add_item_to_list("groceries", "milk")
            add_item_to_list("groceries", "milk")

            # Remove one
            result = remove_item_from_list("groceries", "milk")
            assert result["status"] == "success"

            # Check only one was removed
            items_result = get_list_items("groceries")
            assert items_result["count"] == 2  # Only one removed

    def test_remove_case_insensitive(self, test_config):
        """Removal is case-insensitive but storage is case-sensitive."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("groceries", "Milk")

            # Remove with different case
            result = remove_item_from_list("groceries", "milk")
            assert result["status"] == "success"

            items_result = get_list_items("groceries")
            assert items_result["count"] == 0


class TestEmptyListNames:
    """Tests for empty or unusual list names."""

    def test_empty_list_name(self, test_config):
        """Adding items to a list with empty name should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Empty list names are now rejected
            result = add_item_to_list("", "orphan item")

            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_whitespace_list_name(self, test_config):
        """Adding items to a list with whitespace-only name should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Whitespace-only list names are now rejected
            result = add_item_to_list("   ", "item in whitespace list")

            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_special_characters_in_list_name(self, test_config):
        """List names with special characters."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            special_names = [
                "list/with/slashes",
                "list:with:colons",
                "list\nwith\nnewlines",
                'list"with"quotes',
                "list\\with\\backslashes",
            ]

            for name in special_names:
                result = add_item_to_list(name, "test item")
                assert result["status"] == "success"

            # Verify all lists exist
            lists_result = get_user_lists()
            assert lists_result["total_lists"] == len(special_names)

    def test_very_long_list_name(self, test_config):
        """List with extremely long name."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            long_name = "x" * 10000  # 10K character list name

            result = add_item_to_list(long_name, "item")

            # BUG HUNT: No length validation
            assert result["status"] == "success"
            assert len(result["list_name"]) == 10000


class TestCrossUserDataIsolation:
    """Tests for data isolation between users."""

    def test_users_cannot_see_each_others_lists(self, test_config):
        """User A's lists should not be visible to User B."""
        # User A adds items
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("alice_private", "alice secret")

        # User B checks lists
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="bob@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            lists_result = get_user_lists()
            # Bob should not see Alice's list
            # When no lists exist, response has "message" but no "total_lists"
            list_names = [lst["name"] for lst in lists_result.get("lists", [])]
            assert "alice_private" not in list_names

    def test_users_cannot_see_each_others_todos(self, test_config):
        """User A's todos should not be visible to User B."""
        # User A adds todo
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_todo_item(text="Alice's private todo")

        # User B checks todos
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="bob@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            todos_result = get_user_todos()
            # Bob should not see Alice's todo
            assert todos_result["count"] == 0

    def test_same_list_name_different_users(self, test_config):
        """Two users can have lists with the same name independently."""
        # Alice creates "favorites"
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("favorites", "Alice's favorite")

        # Bob creates "favorites"
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="bob@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("favorites", "Bob's favorite")

        # Verify isolation
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            items = get_list_items("favorites")
            assert items["items"] == ["Alice's favorite"]
            assert "Bob's favorite" not in items["items"]

    def test_user_cannot_complete_another_users_todo(self, test_config):
        """User B cannot complete User A's todos."""
        # Alice creates todo
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_todo_item(text="Alice's important task")

        # Bob tries to complete it
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="bob@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = complete_todo_item("Alice's important task")
            # Bob should not be able to complete Alice's todo
            assert result["status"] == "error"

        # Verify Alice's todo is still incomplete
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            todos = get_user_todos()
            assert todos["count"] == 1
            assert todos["todos"][0]["done"] is False

    def test_user_cannot_remove_from_another_users_list(self, test_config):
        """User B cannot remove items from User A's lists."""
        # Alice adds item
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            add_item_to_list("shopping", "diamonds")

        # Bob tries to remove it
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="bob@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = remove_item_from_list("shopping", "diamonds")
            assert result["status"] == "error"

        # Verify Alice's item is still there
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="alice@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            items = get_list_items("shopping")
            assert items["items"] == ["diamonds"]


class TestEmptyItems:
    """Tests for empty item values."""

    def test_add_empty_item_to_list(self, test_config):
        """Adding empty string as item should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Empty items are now rejected
            result = add_item_to_list("groceries", "")

            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_empty_todo_text(self, test_config):
        """Adding todo with empty text should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Empty todo text is now rejected
            result = add_todo_item(text="")

            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_add_whitespace_only_todo(self, test_config):
        """Adding todo with whitespace-only text should be rejected."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Whitespace-only todo text is now rejected
            result = add_todo_item(text="   \n\t  ")

            assert result["status"] == "error"
            assert "empty" in result["message"].lower()


class TestNegativeReminderDays:
    """Tests for negative reminder_days_before values."""

    def test_negative_reminder_days(self, test_config):
        """Negative reminder days should be rejected."""
        future_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # FIX: Negative days are now rejected
            result = add_todo_item(
                text="Task with weird reminder",
                due_date=future_date,
                reminder_days_before=-2,  # Remind 2 days AFTER due date
            )

            assert result["status"] == "error"
            assert "non-negative" in result["message"].lower()

    def test_very_large_reminder_days(self, test_config):
        """Reminder days before can be very large."""
        future_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # BUG HUNT: 1000 days before = reminder in the past
            result = add_todo_item(
                text="Task with past reminder",
                due_date=future_date,
                reminder_days_before=1000,  # 1000 days before = way in the past
            )

            assert result["status"] == "success"
            # Reminder should not be scheduled (correctly skipped)
            assert "reminder" not in result


class TestNoUserContext:
    """Tests for missing user context."""

    def test_operations_without_user_email(self, test_config):
        """Operations should fail gracefully when user email is not set."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="",  # Empty user email
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            # All operations should return error status
            result = get_user_lists()
            assert result["status"] == "error"

            result = get_list_items("test")
            assert result["status"] == "error"

            result = add_item_to_list("test", "item")
            assert result["status"] == "error"

    def test_todo_operations_without_user_email(self, test_config):
        """Todo operations should fail gracefully when user email is not set."""
        with patch(
            "src.agents.tools.personal_data_tools.get_user_email",
            return_value="",
        ), patch(
            "src.agents.tools.personal_data_tools.get_reply_to",
            return_value="test@example.com",
        ), patch(
            "src.agents.tools.personal_data_tools.get_config"
        ) as mock_config:
            mock_config.return_value = test_config

            result = add_todo_item(text="Test todo")
            assert result["status"] == "error"

            result = get_user_todos()
            assert result["status"] == "error"

            result = complete_todo_item("test")
            assert result["status"] == "error"
