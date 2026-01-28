"""Per-user persistent data storage.

Provides atomic read/write operations for user data including lists and todos.
Data is stored in a single JSON file with per-user namespacing.
"""

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.config import Config

# Lock for thread-safe file operations
_user_data_lock = threading.Lock()


def load_user_data(config: Config) -> dict[str, Any]:
    """Load user data from file, returning empty dict if not found."""
    if not config.user_data_file.exists():
        return {}
    try:
        with open(config.user_data_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def save_user_data(data: dict[str, Any], config: Config) -> None:
    """Save user data atomically using temp file + rename."""
    dir_path = config.user_data_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, config.user_data_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def ensure_user_exists(data: dict[str, Any], email: str) -> None:
    """Initialize user structure if not present."""
    if email not in data:
        data[email] = {"lists": {}, "todos": []}
    data[email].setdefault("lists", {})
    data[email].setdefault("todos", [])


def get_all_lists(email: str, config: Config) -> dict[str, list[str]]:
    """Get all lists with items for a user."""
    data = load_user_data(config)
    if email not in data:
        return {}
    return data[email].get("lists", {})


def get_list_summary(email: str, config: Config) -> list[tuple[str, int]]:
    """Get summary of all lists: [(name, count), ...]."""
    lists = get_all_lists(email, config)
    return [(name, len(items)) for name, items in sorted(lists.items())]


def get_list(email: str, list_name: str, config: Config) -> list[str]:
    """Get items from a specific list."""
    lists = get_all_lists(email, config)
    return lists.get(list_name, [])


def add_to_list(email: str, list_name: str, item: str, config: Config) -> int:
    """Add item to a list, creating list if needed. Returns new count."""
    with _user_data_lock:
        data = load_user_data(config)
        ensure_user_exists(data, email)

        if list_name not in data[email]["lists"]:
            data[email]["lists"][list_name] = []

        data[email]["lists"][list_name].append(item)
        save_user_data(data, config)
        return len(data[email]["lists"][list_name])


def remove_from_list(email: str, list_name: str, item: str, config: Config) -> bool:
    """Remove item from list. Returns True if removed, False if not found."""
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
    """Get todos for a user, optionally including completed ones."""
    data = load_user_data(config)
    if email not in data:
        return []

    todos = data[email].get("todos", [])
    if include_done:
        return todos
    return [t for t in todos if not t.get("done", False)]


def add_todo(
    email: str,
    text: str,
    config: Config,
    due_date: str | None = None,
    reminder_days_before: int | None = None,
) -> dict[str, Any]:
    """Add a todo item. Returns the created todo.

    Args:
        email: User's email address
        text: Todo item text
        config: Application config
        due_date: Optional due date (ISO format YYYY-MM-DD)
        reminder_days_before: Days before due date to send reminder (only if due_date set)
    """
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
    """Mark a todo as done by ID. Returns True if found and marked."""
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
    """Mark a todo as done by matching text. Returns the todo if found."""
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
    """Delete a todo by ID. Returns True if found and deleted."""
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

