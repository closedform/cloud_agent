"""Tests for src/user_data.py"""

import json
from pathlib import Path

import pytest

from src.user_data import (
    _validate_email,
    add_to_list,
    add_todo,
    complete_todo,
    complete_todo_by_text,
    delete_todo,
    ensure_user_exists,
    get_all_lists,
    get_list,
    get_list_summary,
    get_todos,
    load_user_data,
    remove_from_list,
    save_user_data,
)
from src.utils import normalize_email


class TestLoadUserData:
    """Tests for load_user_data function."""

    def test_returns_empty_dict_when_file_missing(self, test_config):
        """Should return empty dict if file doesn't exist."""
        data = load_user_data(test_config)
        assert data == {}

    def test_returns_empty_dict_on_invalid_json(self, test_config):
        """Should return empty dict if file contains invalid JSON."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            f.write("not valid json")
        data = load_user_data(test_config)
        assert data == {}

    def test_loads_valid_data(self, test_config):
        """Should load and return valid JSON data."""
        expected = {"user@example.com": {"lists": {}, "todos": []}}
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            json.dump(expected, f)
        data = load_user_data(test_config)
        assert data == expected


class TestSaveUserData:
    """Tests for save_user_data function."""

    def test_creates_parent_directories(self, test_config):
        """Should create parent directories if they don't exist."""
        data = {"test": "data"}
        save_user_data(data, test_config)
        assert test_config.user_data_file.exists()

    def test_saves_valid_json(self, test_config):
        """Should save data as valid JSON."""
        data = {"user@example.com": {"lists": {"movies": ["Inception"]}, "todos": []}}
        save_user_data(data, test_config)
        with open(test_config.user_data_file) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_atomic_write_no_partial_files(self, test_config):
        """Should not leave partial files on success."""
        data = {"test": "data"}
        save_user_data(data, test_config)
        tmp_files = list(test_config.user_data_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestEnsureUserExists:
    """Tests for ensure_user_exists function."""

    def test_creates_user_if_missing(self):
        """Should create user structure if not present."""
        data = {}
        ensure_user_exists(data, "new@example.com")
        assert "new@example.com" in data
        assert data["new@example.com"] == {"lists": {}, "todos": []}

    def test_preserves_existing_user(self):
        """Should not modify existing user data."""
        data = {
            "existing@example.com": {
                "lists": {"movies": ["Inception"]},
                "todos": [{"id": "1", "text": "test"}],
            }
        }
        ensure_user_exists(data, "existing@example.com")
        assert data["existing@example.com"]["lists"] == {"movies": ["Inception"]}

    def test_adds_missing_lists_key(self):
        """Should add lists key if missing."""
        data = {"user@example.com": {"todos": []}}
        ensure_user_exists(data, "user@example.com")
        assert "lists" in data["user@example.com"]

    def test_adds_missing_todos_key(self):
        """Should add todos key if missing."""
        data = {"user@example.com": {"lists": {}}}
        ensure_user_exists(data, "user@example.com")
        assert "todos" in data["user@example.com"]


class TestListOperations:
    """Tests for list-related functions."""

    def test_get_all_lists_empty_for_new_user(self, test_config):
        """Should return empty dict for user with no lists."""
        lists = get_all_lists("nonexistent@example.com", test_config)
        assert lists == {}

    def test_get_all_lists_returns_user_lists(self, test_config, populated_user_data):
        """Should return all lists for a user."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        lists = get_all_lists("user1@example.com", test_config)
        assert "movies" in lists
        assert "books" in lists
        assert lists["movies"] == ["Inception", "The Matrix"]

    def test_get_list_summary(self, test_config, populated_user_data):
        """Should return list names with counts."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        summary = get_list_summary("user1@example.com", test_config)
        summary_dict = dict(summary)
        assert summary_dict["movies"] == 2
        assert summary_dict["books"] == 1

    def test_get_list_returns_items(self, test_config, populated_user_data):
        """Should return items from a specific list."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        items = get_list("user1@example.com", "movies", test_config)
        assert items == ["Inception", "The Matrix"]

    def test_get_list_empty_for_missing_list(self, test_config):
        """Should return empty list for nonexistent list."""
        items = get_list("user@example.com", "nonexistent", test_config)
        assert items == []

    def test_add_to_list_creates_list(self, test_config):
        """Should create list if it doesn't exist."""
        count = add_to_list("user@example.com", "newlist", "item1", test_config)
        assert count == 1
        items = get_list("user@example.com", "newlist", test_config)
        assert items == ["item1"]

    def test_add_to_list_appends_item(self, test_config, populated_user_data):
        """Should append item to existing list."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        count = add_to_list("user1@example.com", "movies", "Interstellar", test_config)
        assert count == 3
        items = get_list("user1@example.com", "movies", test_config)
        assert "Interstellar" in items

    def test_remove_from_list_removes_item(self, test_config, populated_user_data):
        """Should remove item from list."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = remove_from_list("user1@example.com", "movies", "Inception", test_config)
        assert result is True
        items = get_list("user1@example.com", "movies", test_config)
        assert "Inception" not in items

    def test_remove_from_list_case_insensitive(self, test_config, populated_user_data):
        """Should match items case-insensitively."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = remove_from_list("user1@example.com", "movies", "INCEPTION", test_config)
        assert result is True

    def test_remove_from_list_returns_false_if_not_found(self, test_config):
        """Should return False if item not in list."""
        result = remove_from_list("user@example.com", "movies", "NotThere", test_config)
        assert result is False


class TestTodoOperations:
    """Tests for todo-related functions."""

    def test_get_todos_empty_for_new_user(self, test_config):
        """Should return empty list for user with no todos."""
        todos = get_todos("nonexistent@example.com", test_config)
        assert todos == []

    def test_get_todos_excludes_done_by_default(self, test_config, populated_user_data):
        """Should exclude completed todos by default."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        todos = get_todos("user1@example.com", test_config)
        assert len(todos) == 1
        assert todos[0]["text"] == "Call Einstein"

    def test_get_todos_includes_done_when_requested(self, test_config, populated_user_data):
        """Should include completed todos when include_done=True."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        todos = get_todos("user1@example.com", test_config, include_done=True)
        assert len(todos) == 2

    def test_add_todo_creates_todo(self, test_config):
        """Should create a new todo with generated ID."""
        todo = add_todo("user@example.com", "New task", test_config)
        assert todo["text"] == "New task"
        assert todo["done"] is False
        assert "id" in todo
        assert "created_at" in todo

    def test_add_todo_with_due_date(self, test_config):
        """Should create todo with due date."""
        todo = add_todo(
            "user@example.com",
            "Task with date",
            test_config,
            due_date="2026-02-15",
        )
        assert todo["due_date"] == "2026-02-15"

    def test_add_todo_with_reminder(self, test_config):
        """Should create todo with reminder days."""
        todo = add_todo(
            "user@example.com",
            "Task with reminder",
            test_config,
            due_date="2026-02-15",
            reminder_days_before=2,
        )
        assert todo["due_date"] == "2026-02-15"
        assert todo["reminder_days_before"] == 2

    def test_add_todo_no_reminder_without_due_date(self, test_config):
        """Should not add reminder if no due date."""
        todo = add_todo(
            "user@example.com",
            "Task",
            test_config,
            reminder_days_before=2,
        )
        assert "reminder_days_before" not in todo

    def test_complete_todo_by_id(self, test_config, populated_user_data):
        """Should mark todo as done by ID."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = complete_todo("user1@example.com", "todo-1", test_config)
        assert result is True
        todos = get_todos("user1@example.com", test_config, include_done=True)
        todo = next(t for t in todos if t["id"] == "todo-1")
        assert todo["done"] is True

    def test_complete_todo_returns_false_if_not_found(self, test_config):
        """Should return False if todo not found."""
        result = complete_todo("user@example.com", "nonexistent-id", test_config)
        assert result is False

    def test_complete_todo_by_text(self, test_config, populated_user_data):
        """Should mark todo as done by matching text."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = complete_todo_by_text("user1@example.com", "Einstein", test_config)
        assert result is not None
        assert result["text"] == "Call Einstein"

    def test_complete_todo_by_text_case_insensitive(self, test_config, populated_user_data):
        """Should match text case-insensitively."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = complete_todo_by_text("user1@example.com", "EINSTEIN", test_config)
        assert result is not None

    def test_complete_todo_by_text_skips_done(self, test_config, populated_user_data):
        """Should not match already-completed todos."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = complete_todo_by_text("user1@example.com", "groceries", test_config)
        assert result is None

    def test_delete_todo(self, test_config, populated_user_data):
        """Should delete todo by ID."""
        test_config = test_config.__class__(
            **{**test_config.__dict__, "user_data_file": populated_user_data}
        )
        result = delete_todo("user1@example.com", "todo-1", test_config)
        assert result is True
        todos = get_todos("user1@example.com", test_config, include_done=True)
        assert not any(t["id"] == "todo-1" for t in todos)

    def test_delete_todo_returns_false_if_not_found(self, test_config):
        """Should return False if todo not found."""
        result = delete_todo("user@example.com", "nonexistent", test_config)
        assert result is False


class TestEmailNormalization:
    """Tests for email normalization and validation."""

    def test_normalize_email_lowercase(self):
        """Should lowercase email addresses."""
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_normalize_email_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert normalize_email("  user@example.com  ") == "user@example.com"

    def test_validate_email_valid_addresses(self):
        """Should accept valid email formats."""
        assert _validate_email("user@example.com") is True
        assert _validate_email("user.name@example.co.uk") is True
        assert _validate_email("user+tag@example.com") is True

    def test_validate_email_invalid_addresses(self):
        """Should reject invalid email formats."""
        assert _validate_email("invalid") is False
        assert _validate_email("@example.com") is False
        assert _validate_email("user@") is False
        assert _validate_email("user @example.com") is False
        assert _validate_email("") is False


class TestEmailCaseInsensitivity:
    """Tests for case-insensitive email handling."""

    def test_add_to_list_normalizes_email(self, test_config):
        """Should normalize email when adding to list."""
        add_to_list("USER@EXAMPLE.COM", "movies", "Inception", test_config)
        # Should find with lowercase lookup
        items = get_list("user@example.com", "movies", test_config)
        assert items == ["Inception"]

    def test_add_todo_normalizes_email(self, test_config):
        """Should normalize email when adding todo."""
        add_todo("USER@EXAMPLE.COM", "Test task", test_config)
        # Should find with lowercase lookup
        todos = get_todos("user@example.com", test_config)
        assert len(todos) == 1
        assert todos[0]["text"] == "Test task"

    def test_complete_todo_normalizes_email(self, test_config):
        """Should normalize email when completing todo."""
        todo = add_todo("user@example.com", "Task to complete", test_config)
        # Complete with uppercase email
        result = complete_todo("USER@EXAMPLE.COM", todo["id"], test_config)
        assert result is True

    def test_delete_todo_normalizes_email(self, test_config):
        """Should normalize email when deleting todo."""
        todo = add_todo("user@example.com", "Task to delete", test_config)
        # Delete with uppercase email
        result = delete_todo("USER@EXAMPLE.COM", todo["id"], test_config)
        assert result is True


class TestDataValidation:
    """Tests for input validation."""

    def test_add_to_list_invalid_email_raises(self, test_config):
        """Should raise ValueError for invalid email format."""
        with pytest.raises(ValueError, match="Invalid email format"):
            add_to_list("invalid-email", "movies", "Inception", test_config)

    def test_add_todo_invalid_email_raises(self, test_config):
        """Should raise ValueError for invalid email format."""
        with pytest.raises(ValueError, match="Invalid email format"):
            add_todo("invalid-email", "Test task", test_config)

    def test_add_todo_invalid_due_date_raises(self, test_config):
        """Should raise ValueError for invalid due date format."""
        with pytest.raises(ValueError, match="Invalid due_date format"):
            add_todo(
                "user@example.com",
                "Test task",
                test_config,
                due_date="2026/02/15",  # Wrong format
            )

    def test_add_todo_invalid_due_date_value_raises(self, test_config):
        """Should raise ValueError for invalid due date value."""
        with pytest.raises(ValueError, match="Invalid due_date format"):
            add_todo(
                "user@example.com",
                "Test task",
                test_config,
                due_date="2026-13-45",  # Invalid month/day
            )

    def test_add_todo_valid_due_date_accepted(self, test_config):
        """Should accept valid due date format."""
        todo = add_todo(
            "user@example.com",
            "Test task",
            test_config,
            due_date="2026-02-15",
        )
        assert todo["due_date"] == "2026-02-15"


class TestUnicodeSupport:
    """Tests for Unicode character support."""

    def test_save_and_load_unicode_data(self, test_config):
        """Should correctly save and load Unicode characters."""
        data = {
            "user@example.com": {
                "lists": {"peliculas": ["El laberinto del fauno", "Amelie"]},
                "todos": [{"id": "1", "text": "Llamar a mama", "done": False}],
            }
        }
        save_user_data(data, test_config)
        loaded = load_user_data(test_config)
        assert loaded == data

    def test_add_unicode_items(self, test_config):
        """Should handle Unicode in list items."""
        add_to_list("user@example.com", "movies", "Amelie", test_config)
        items = get_list("user@example.com", "movies", test_config)
        assert "Amelie" in items

    def test_add_unicode_todo(self, test_config):
        """Should handle Unicode in todo text."""
        todo = add_todo("user@example.com", "Buy cafe con leche", test_config)
        assert todo["text"] == "Buy cafe con leche"
