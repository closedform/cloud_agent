"""Per-user persistent data storage.

Provides atomic read/write operations for user data including lists and todos.
Data is stored in a single JSON file with per-user namespacing.
"""

import json
import re
import threading
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.config import Config
from src.utils import atomic_write_json, normalize_email

# Lock for thread-safe file operations
_user_data_lock = threading.Lock()

# Simple email validation pattern
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> bool:
    """Basic email format validation."""
    return bool(_EMAIL_PATTERN.match(email))


def load_user_data(config: Config) -> dict[str, Any]:
    """Load user data from file, returning empty dict if not found.

    Note: This function should be called within _user_data_lock for write operations
    to ensure atomicity. Read-only operations can call without lock for better
    performance, accepting eventual consistency.
    """
    if not config.user_data_file.exists():
        return {}
    try:
        with open(config.user_data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate structure
        if not isinstance(data, dict):
            print(f"Warning: User data file has invalid structure (expected dict), returning empty")
            return {}
        return data
    except json.JSONDecodeError as e:
        print(f"Warning: User data file has invalid JSON: {e}")
        return {}
    except UnicodeDecodeError as e:
        print(f"Warning: User data file has encoding issues: {e}")
        return {}
    except OSError as e:
        print(f"Warning: Cannot read user data file: {e}")
        return {}


def save_user_data(data: dict[str, Any], config: Config) -> None:
    """Save user data atomically.

    Must be called within _user_data_lock to ensure atomicity with reads.
    """
    atomic_write_json(data, config.user_data_file)


def ensure_user_exists(data: dict[str, Any], email: str) -> None:
    """Initialize user structure if not present.

    Args:
        data: The user data dictionary to modify in place.
        email: Email address (should already be normalized by caller).
    """
    if email not in data:
        data[email] = {"lists": {}, "todos": []}
    data[email].setdefault("lists", {})
    data[email].setdefault("todos", [])


def get_all_lists(email: str, config: Config) -> dict[str, list[str]]:
    """Get all lists with items for a user.

    Args:
        email: User's email address (will be normalized).
        config: Application configuration.

    Returns:
        Dictionary mapping list names to list of items. Returns empty dict
        if user not found.
    """
    email = normalize_email(email)
    data = load_user_data(config)
    if email not in data:
        return {}
    return data[email].get("lists", {})


def get_list_summary(email: str, config: Config) -> list[tuple[str, int]]:
    """Get summary of all lists: [(name, count), ...].

    Args:
        email: User's email address (will be normalized).
        config: Application configuration.

    Returns:
        List of tuples (list_name, item_count) sorted alphabetically by name.
    """
    lists = get_all_lists(email, config)  # email normalized in get_all_lists
    return [(name, len(items)) for name, items in sorted(lists.items())]


def get_list(email: str, list_name: str, config: Config) -> list[str]:
    """Get items from a specific list.

    Args:
        email: User's email address (will be normalized).
        list_name: Name of the list (case-sensitive).
        config: Application configuration.

    Returns:
        List of items, or empty list if list not found.
    """
    lists = get_all_lists(email, config)  # email normalized in get_all_lists
    return lists.get(list_name, [])


def add_to_list(email: str, list_name: str, item: str, config: Config) -> int:
    """Add item to a list, creating list if needed.

    Args:
        email: User's email address (will be normalized).
        list_name: Name of the list (case-sensitive).
        item: Item to add.
        config: Application configuration.

    Returns:
        New count of items in the list.

    Raises:
        ValueError: If email format is invalid.
    """
    email = normalize_email(email)
    if not _validate_email(email):
        raise ValueError(f"Invalid email format: {email}")

    with _user_data_lock:
        data = load_user_data(config)
        ensure_user_exists(data, email)

        if list_name not in data[email]["lists"]:
            data[email]["lists"][list_name] = []

        data[email]["lists"][list_name].append(item)
        save_user_data(data, config)
        return len(data[email]["lists"][list_name])


def remove_from_list(email: str, list_name: str, item: str, config: Config) -> bool:
    """Remove item from list.

    Uses case-insensitive matching to find the item to remove.

    Args:
        email: User's email address (will be normalized).
        list_name: Name of the list (case-sensitive).
        item: Item to remove (case-insensitive match).
        config: Application configuration.

    Returns:
        True if item was found and removed, False otherwise.
    """
    email = normalize_email(email)
    with _user_data_lock:
        data = load_user_data(config)
        if email not in data:
            return False

        lists = data[email].get("lists", {})
        if list_name not in lists:
            return False

        items = lists[list_name]
        item_lower = item.lower()
        for i, existing in enumerate(items):
            if existing.lower() == item_lower:
                items.pop(i)
                save_user_data(data, config)
                return True
        return False


def get_todos(
    email: str, config: Config, include_done: bool = False
) -> list[dict[str, Any]]:
    """Get todos for a user, optionally including completed ones.

    Args:
        email: User's email address (will be normalized).
        config: Application configuration.
        include_done: If True, include completed todos. Default False.

    Returns:
        List of todo dictionaries. Returns empty list if user not found.
    """
    email = normalize_email(email)
    data = load_user_data(config)
    if email not in data:
        return []

    todos = data[email].get("todos", [])
    if include_done:
        return todos
    return [t for t in todos if not t.get("done", False)]


def _validate_due_date(due_date: str) -> bool:
    """Validate due_date is in YYYY-MM-DD format."""
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def add_todo(
    email: str,
    text: str,
    config: Config,
    due_date: str | None = None,
    reminder_days_before: int | None = None,
) -> dict[str, Any]:
    """Add a todo item. Returns the created todo.

    Args:
        email: User's email address (will be normalized).
        text: Todo item text.
        config: Application config.
        due_date: Optional due date in ISO format (YYYY-MM-DD).
        reminder_days_before: Days before due date to send reminder (only if due_date set).

    Returns:
        The created todo dictionary with id, text, done, created_at, and optionally
        due_date and reminder_days_before.

    Raises:
        ValueError: If email format is invalid or due_date format is invalid.
    """
    email = normalize_email(email)
    if not _validate_email(email):
        raise ValueError(f"Invalid email format: {email}")

    if due_date is not None and not _validate_due_date(due_date):
        raise ValueError(f"Invalid due_date format: {due_date}. Expected YYYY-MM-DD.")

    with _user_data_lock:
        data = load_user_data(config)
        ensure_user_exists(data, email)

        local_tz = ZoneInfo(config.timezone)
        todo: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "text": text,
            "done": False,
            "created_at": datetime.now(local_tz).isoformat(),
        }

        if due_date:
            todo["due_date"] = due_date
            if reminder_days_before is not None:
                todo["reminder_days_before"] = reminder_days_before

        data[email]["todos"].append(todo)
        save_user_data(data, config)
        return todo


def complete_todo(email: str, todo_id: str, config: Config) -> bool:
    """Mark a todo as done by ID.

    Args:
        email: User's email address (will be normalized).
        todo_id: The unique ID of the todo to complete.
        config: Application configuration.

    Returns:
        True if todo was found and marked complete, False otherwise.
    """
    email = normalize_email(email)
    with _user_data_lock:
        data = load_user_data(config)
        if email not in data:
            return False

        local_tz = ZoneInfo(config.timezone)
        for todo in data[email].get("todos", []):
            if todo.get("id") == todo_id:
                todo["done"] = True
                todo["completed_at"] = datetime.now(local_tz).isoformat()
                save_user_data(data, config)
                return True
        return False


def complete_todo_by_text(email: str, text: str, config: Config) -> dict[str, Any] | None:
    """Mark a todo as done by matching text.

    Uses case-insensitive partial matching to find the first incomplete todo
    that contains the search text.

    Args:
        email: User's email address (will be normalized).
        text: Text to search for (case-insensitive partial match).
        config: Application configuration.

    Returns:
        The completed todo dictionary if found, None otherwise.
    """
    email = normalize_email(email)
    with _user_data_lock:
        data = load_user_data(config)
        if email not in data:
            return None

        local_tz = ZoneInfo(config.timezone)
        text_lower = text.lower()
        for todo in data[email].get("todos", []):
            if not todo.get("done", False) and text_lower in todo.get("text", "").lower():
                todo["done"] = True
                todo["completed_at"] = datetime.now(local_tz).isoformat()
                save_user_data(data, config)
                return todo
        return None


def delete_todo(email: str, todo_id: str, config: Config) -> bool:
    """Delete a todo by ID.

    Args:
        email: User's email address (will be normalized).
        todo_id: The unique ID of the todo to delete.
        config: Application configuration.

    Returns:
        True if todo was found and deleted, False otherwise.
    """
    email = normalize_email(email)
    with _user_data_lock:
        data = load_user_data(config)
        if email not in data:
            return False

        todos = data[email].get("todos", [])
        for i, todo in enumerate(todos):
            if todo.get("id") == todo_id:
                todos.pop(i)
                save_user_data(data, config)
                return True
        return False

