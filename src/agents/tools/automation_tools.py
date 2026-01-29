"""Automation tool functions for AutomationAgent.

Handles reminders and rules operations.
"""

from datetime import datetime
from typing import Any

from src.agents.tools._context import get_user_email, get_reply_to
from src.config import get_config
from src.reminders import add_reminder
from src.models import Reminder
from src.rules import Rule, add_rule, delete_rule, get_user_rules

# Valid actions for rules
VALID_RULE_ACTIONS = {"weekly_schedule_summary", "send_reminder", "generate_diary"}


def _validate_datetime(datetime_str: str) -> tuple[bool, str]:
    """Validate an ISO datetime string.

    Args:
        datetime_str: ISO format datetime string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        return True, ""
    except ValueError as e:
        return False, f"Invalid datetime format: {e}"


def create_reminder(
    message: str,
    reminder_time: str,
) -> dict[str, Any]:
    """Create a new reminder.

    Args:
        message: Reminder message/subject (cannot be empty).
        reminder_time: When to send reminder in ISO format (YYYY-MM-DDTHH:MM:SS).

    Returns:
        Dictionary with created reminder details.
    """
    reply_to = get_reply_to()
    if not reply_to:
        return {"status": "error", "message": "Reply address not available"}

    # Validate message is not empty
    if not message or not message.strip():
        return {"status": "error", "message": "Reminder message cannot be empty"}

    # Validate datetime format
    is_valid, error_msg = _validate_datetime(reminder_time)
    if not is_valid:
        return {"status": "error", "message": error_msg}

    config = get_config()

    try:
        # Create new reminder
        reminder = Reminder.create(
            message=message,
            reminder_datetime=reminder_time,
            reply_to=reply_to,
        )

        # Add reminder atomically (handles persistence and scheduling)
        add_reminder(reminder, config)

        return {
            "status": "success",
            "message": f"Reminder set for {reminder_time}",
            "reminder": {
                "id": reminder.id,
                "message": message,
                "time": reminder_time,
            },
        }

    except Exception as e:
        return {"status": "error", "message": f"Failed to create reminder: {e}"}


def get_rules() -> dict[str, Any]:
    """Get all automation rules for the current user.

    Returns:
        Dictionary with user's rules.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()

    try:
        rules = get_user_rules(email, config)
        return {
            "status": "success",
            "rules": [r.to_dict() for r in rules],
            "count": len(rules),
        }
    except (KeyError, TypeError) as e:
        # Handle corrupted rule data gracefully
        return {"status": "error", "message": f"Error loading rules: {e}"}


def create_rule(
    rule_type: str,
    action: str,
    schedule: str | None = None,
    description: str | None = None,
    days_before: int | None = None,
    message_template: str | None = None,
) -> dict[str, Any]:
    """Create a new automation rule.

    Args:
        rule_type: Type of rule - "time" for cron-based or "event" for calendar event triggers.
        action: Action to perform - "weekly_schedule_summary", "send_reminder", "generate_diary".
        schedule: Cron expression for time-based rules (e.g., "0 8 * * 0" for Sunday 8am).
        description: Event description for AI matching (event rules only).
        days_before: Days before event to trigger (event rules only, must be >= 0).
        message_template: Message template for send_reminder action.

    Returns:
        Dictionary with created rule details.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    # Validate action
    if not action or not action.strip():
        return {"status": "error", "message": "Action cannot be empty"}

    if action not in VALID_RULE_ACTIONS:
        return {
            "status": "error",
            "message": f"Unknown action: {action}. Valid actions: {', '.join(sorted(VALID_RULE_ACTIONS))}",
        }

    config = get_config()

    try:
        params = {}
        if message_template:
            params["message_template"] = message_template

        if rule_type == "time":
            if not schedule:
                return {"status": "error", "message": "Schedule required for time rules"}

            # Rule.create_time_rule validates cron expression and raises ValueError if invalid
            rule = Rule.create_time_rule(
                user_email=email,
                schedule=schedule,
                action=action,
                params=params,
            )
        elif rule_type == "event":
            if not description:
                return {"status": "error", "message": "Description required for event rules"}

            trigger = {}
            if days_before is not None:
                # Validate days_before is non-negative
                if days_before < 0:
                    return {
                        "status": "error",
                        "message": "days_before must be >= 0 (use 0 for day-of event)",
                    }
                trigger["days_before"] = days_before

            rule = Rule.create_event_rule(
                user_email=email,
                description=description,
                trigger=trigger,
                action=action,
                params=params,
            )
        else:
            return {"status": "error", "message": f"Unknown rule type: {rule_type}"}

        add_rule(rule, config)

        return {
            "status": "success",
            "message": f"Created {rule_type} rule: {action}",
            "rule": rule.to_dict(),
        }

    except Exception as e:
        return {"status": "error", "message": f"Failed to create rule: {e}"}


def delete_user_rule(rule_id: str) -> dict[str, Any]:
    """Delete an automation rule by ID.

    Args:
        rule_id: ID of the rule to delete.

    Returns:
        Dictionary with deletion status.
        status will be "success" if deleted, "error" if not found or other issue.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()
    deleted = delete_rule(email, rule_id, config)

    if deleted:
        return {
            "status": "success",
            "message": f"Deleted rule {rule_id}",
            "rule_id": rule_id,
        }
    else:
        return {
            "status": "error",
            "message": f"Rule {rule_id} not found or already deleted",
            "rule_id": rule_id,
        }

