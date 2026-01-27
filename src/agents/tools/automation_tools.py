"""Automation tool functions for AutomationAgent.

Handles reminders and rules operations.
"""

from typing import Any

from src.agents.tools._context import get_user_email, get_reply_to
from src.config import get_config
from src.reminders import add_reminder
from src.models import Reminder
from src.rules import Rule, add_rule, delete_rule, get_user_rules


def create_reminder(
    message: str,
    reminder_time: str,
) -> dict[str, Any]:
    """Create a new reminder.

    Args:
        message: Reminder message/subject.
        reminder_time: When to send reminder in ISO format (YYYY-MM-DDTHH:MM:SS).

    Returns:
        Dictionary with created reminder details.
    """
    reply_to = get_reply_to()
    if not reply_to:
        return {"status": "error", "message": "Reply address not available"}

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
    rules = get_user_rules(email, config)

    return {
        "status": "success",
        "rules": [r.to_dict() for r in rules],
        "count": len(rules),
    }


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
        days_before: Days before event to trigger (event rules only).
        message_template: Message template for send_reminder action.

    Returns:
        Dictionary with created rule details.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    config = get_config()

    try:
        params = {}
        if message_template:
            params["message_template"] = message_template

        if rule_type == "time":
            if not schedule:
                return {"status": "error", "message": "Schedule required for time rules"}

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
            "status": "not_found",
            "message": f"Rule {rule_id} not found",
            "rule_id": rule_id,
        }

