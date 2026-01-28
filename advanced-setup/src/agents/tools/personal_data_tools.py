"""Personal data tool functions for PersonalDataAgent.

Handles lists and todos operations.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.agents.tools._context import get_user_email, get_reply_to
from src.config import get_config
from src.models import Reminder
from src.reminders import add_reminder
from src.user_data import (
    add_to_list,
    add_todo,
    complete_todo_by_text,
    get_all_lists,
    get_list,
    get_list_summary,
    get_todos,
    remove_from_list,
)


def get_user_lists() -> dict[str, Any]:
    """Get all lists for the current user.

    Returns:
        Dictionary with list names and item counts.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    summary = get_list_summary(email, config)

    if not summary:
        return {
            "status": "success",
            "message": "No lists found",
            "lists": [],
        }

    return {
        "status": "success",
        "lists": [{"name": name, "count": count} for name, count in summary],
        "total_lists": len(summary),
    }


def get_list_items(list_name: str) -> dict[str, Any]:
    """Get items from a specific list.

    Args:
        list_name: Name of the list to retrieve.

    Returns:
        Dictionary with list items.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    items = get_list(email, list_name, config)

    return {
        "status": "success",
        "list_name": list_name,
        "items": items,
        "count": len(items),
    }


def add_item_to_list(list_name: str, item: str) -> dict[str, Any]:
    """Add an item to a list, creating the list if needed.

    Args:
        list_name: Name of the list.
        item: Item to add.

    Returns:
        Dictionary with status and updated count.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    count = add_to_list(email, list_name, item, config)

    return {
        "status": "success",
        "message": f"Added '{item}' to {list_name}",
        "list_name": list_name,
        "item": item,
        "total_count": count,
    }


def remove_item_from_list(list_name: str, item: str) -> dict[str, Any]:
    """Remove an item from a list.

    Args:
        list_name: Name of the list.
        item: Item to remove (case-insensitive match).

    Returns:
        Dictionary with status.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    removed = remove_from_list(email, list_name, item, config)

    if removed:
        return {
            "status": "success",
            "message": f"Removed '{item}' from {list_name}",
            "list_name": list_name,
            "item": item,
        }
    else:
        return {
            "status": "not_found",
            "message": f"'{item}' not found in {list_name}",
            "list_name": list_name,
            "item": item,
        }


def get_user_todos(include_completed: bool = False) -> dict[str, Any]:
    """Get todos for the current user.

    Args:
        include_completed: Whether to include completed todos.

    Returns:
        Dictionary with todos.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    todos = get_todos(email, config, include_done=include_completed)

    return {
        "status": "success",
        "todos": todos,
        "count": len(todos),
        "include_completed": include_completed,
    }


def add_todo_item(
    text: str,
    due_date: str | None = None,
    reminder_days_before: int | None = None,
) -> dict[str, Any]:
    """Add a new todo item.

    Args:
        text: Todo item text.
        due_date: Optional due date in ISO format (YYYY-MM-DD).
        reminder_days_before: Optional days before due date to send reminder.

    Returns:
        Dictionary with created todo.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    reply_to = get_reply_to()
    config = get_config()
    todo = add_todo(email, text, config, due_date, reminder_days_before)

    # Schedule reminder if due_date and reminder_days_before are provided
    reminder_scheduled = False
    if due_date and reminder_days_before is not None and reply_to:
        # Parse due date
        try:
            due = datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            # Invalid date format, skip reminder scheduling
            due = None

        if due is not None:
            try:
                # Calculate reminder time (9 AM on reminder day) with timezone
                tz = ZoneInfo(config.timezone)
                reminder_date = due - timedelta(days=reminder_days_before)
                reminder_time = reminder_date.replace(
                    hour=9, minute=0, second=0, tzinfo=tz
                )

                # Only schedule if reminder is in the future (timezone-aware comparison)
                now = datetime.now(tz)
                if reminder_time > now:
                    reminder = Reminder.create(
                        message=f"Todo reminder: {text} (due {due_date})",
                        reminder_datetime=reminder_time.isoformat(),
                        reply_to=reply_to,
                    )
                    add_reminder(reminder, config)
                    reminder_scheduled = True
            except Exception as e:
                # Log but don't fail the todo creation
                print(f"Failed to schedule todo reminder: {e}")

    result: dict[str, Any] = {
        "status": "success",
        "message": f"Added todo: {text}",
        "todo": todo,
    }
    if reminder_scheduled:
        result["reminder"] = f"Reminder scheduled for {reminder_days_before} day(s) before due date"
    elif due_date and reminder_days_before is not None:
        result["reminder_note"] = "Reminder could not be scheduled (may be in the past or invalid)"

    return result


def complete_todo_item(text_or_id: str) -> dict[str, Any]:
    """Mark a todo as complete by matching text.

    Args:
        text_or_id: Text to match (partial match) or todo ID.

    Returns:
        Dictionary with completed todo or not found message.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    completed = complete_todo_by_text(email, text_or_id, config)

    if completed:
        return {
            "status": "success",
            "message": f"Completed: {completed['text']}",
            "todo": completed,
        }
    else:
        return {
            "status": "not_found",
            "message": f"No matching incomplete todo found for '{text_or_id}'",
        }

