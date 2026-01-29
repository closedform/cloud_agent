"""Rule storage and CRUD operations.

Rules define automated actions triggered by time (cron) or calendar events.
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter, CroniterBadCronError

from src.config import Config
from src.utils import atomic_write_json


# Valid rule types
VALID_RULE_TYPES = ("time", "event")


def validate_cron_expression(expr: str) -> tuple[bool, str | None]:
    """Validate a cron expression.

    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    try:
        # croniter validates on instantiation
        croniter(expr)
        return True, None
    except CroniterBadCronError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Invalid cron expression: {e}"

# Lock for thread-safe file operations
_rules_lock = threading.Lock()


@dataclass
class Rule:
    """Represents an automation rule."""

    id: str
    user_email: str
    type: str  # "time" or "event"
    action: str  # "weekly_schedule_summary", "send_reminder", "generate_diary"
    enabled: bool = True
    schedule: str | None = None  # Cron expression for time-based rules
    description: str | None = None  # Event description for AI matching
    trigger: dict[str, Any] = field(default_factory=dict)  # e.g., {"days_before": 3}
    params: dict[str, Any] = field(default_factory=dict)  # Action parameters
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_fired: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "user_email": self.user_email,
            "type": self.type,
            "action": self.action,
            "enabled": self.enabled,
            "schedule": self.schedule,
            "description": self.description,
            "trigger": self.trigger,
            "params": self.params,
            "created_at": self.created_at,
            "last_fired": self.last_fired,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        """Create Rule from dictionary."""
        return cls(
            id=data["id"],
            user_email=data["user_email"],
            type=data["type"],
            action=data["action"],
            enabled=data.get("enabled", True),
            schedule=data.get("schedule"),
            description=data.get("description"),
            trigger=data.get("trigger", {}),
            params=data.get("params", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_fired=data.get("last_fired"),
        )

    @classmethod
    def create_time_rule(
        cls,
        user_email: str,
        schedule: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> "Rule":
        """Create a time-based rule with cron schedule.

        Raises ValueError if the cron expression is invalid.
        """
        valid, error = validate_cron_expression(schedule)
        if not valid:
            raise ValueError(f"Invalid cron schedule '{schedule}': {error}")

        return cls(
            id=str(int(time.time() * 1000)),
            user_email=user_email,
            type="time",
            action=action,
            schedule=schedule,
            params=params or {},
        )

    @classmethod
    def create_event_rule(
        cls,
        user_email: str,
        description: str,
        trigger: dict[str, Any],
        action: str,
        params: dict[str, Any] | None = None,
    ) -> "Rule":
        """Create an event-based rule with AI matching."""
        return cls(
            id=str(int(time.time() * 1000)),
            user_email=user_email,
            type="event",
            action=action,
            description=description,
            trigger=trigger,
            params=params or {},
        )


def load_rules(config: Config) -> dict[str, list[dict[str, Any]]]:
    """Load all rules from file, returning empty dict if not found.

    Note: This is NOT thread-safe. Use load_rules_safe() for concurrent access.

    Validates structure and filters out malformed entries to prevent crashes
    when deserializing rules.
    """
    if not config.rules_file.exists():
        return {}
    try:
        with open(config.rules_file, "r") as f:
            data = json.load(f)
        # Validate structure
        if not isinstance(data, dict):
            print("Warning: Rules file has invalid structure (expected dict), returning empty")
            return {}

        # Validate and filter each user's rules list
        validated: dict[str, list[dict[str, Any]]] = {}
        for email, rules_list in data.items():
            if not isinstance(rules_list, list):
                print(f"Warning: Rules for {email} is not a list, skipping")
                continue
            valid_rules = []
            for rule in rules_list:
                if not isinstance(rule, dict):
                    print(f"Warning: Invalid rule entry for {email} (not a dict), skipping")
                    continue
                # Check required fields exist
                required = ("id", "user_email", "type", "action")
                if not all(k in rule for k in required):
                    missing = [k for k in required if k not in rule]
                    print(f"Warning: Rule for {email} missing required fields {missing}, skipping")
                    continue
                valid_rules.append(rule)
            if valid_rules:
                validated[email] = valid_rules

        return validated
    except json.JSONDecodeError as e:
        print(f"Warning: Rules file has invalid JSON: {e}")
        return {}
    except OSError as e:
        print(f"Warning: Cannot read rules file: {e}")
        return {}


def load_rules_safe(config: Config) -> dict[str, list[dict[str, Any]]]:
    """Thread-safe version of load_rules.

    Use this when reading rules from a background thread while other threads
    may be modifying the rules file.
    """
    with _rules_lock:
        return load_rules(config)


def save_rules(data: dict[str, list[dict[str, Any]]], config: Config) -> None:
    """Save rules atomically."""
    atomic_write_json(data, config.rules_file)


def get_user_rules(email: str, config: Config) -> list[Rule]:
    """Get all rules for a user.

    Thread-safe: acquires lock to prevent reading while another thread writes.
    """
    with _rules_lock:
        data = load_rules(config)
    rules_data = data.get(email, [])
    return [Rule.from_dict(r) for r in rules_data]


def add_rule(rule: Rule, config: Config) -> None:
    """Add a rule for a user."""
    with _rules_lock:
        data = load_rules(config)
        if rule.user_email not in data:
            data[rule.user_email] = []
        data[rule.user_email].append(rule.to_dict())
        save_rules(data, config)


def delete_rule(email: str, rule_id: str, config: Config) -> bool:
    """Delete a rule by ID. Returns True if found and deleted."""
    with _rules_lock:
        data = load_rules(config)
        if email not in data:
            return False

        rules = data[email]
        for i, rule in enumerate(rules):
            if rule.get("id") == rule_id:
                rules.pop(i)
                save_rules(data, config)
                return True
        return False


def update_rule_last_fired(email: str, rule_id: str, config: Config) -> None:
    """Update the last_fired timestamp for a rule.

    Stores timezone-aware datetime to ensure consistent comparison with
    scheduler's timezone-aware now().
    """
    with _rules_lock:
        data = load_rules(config)
        if email not in data:
            return

        local_tz = ZoneInfo(config.timezone)
        for rule in data[email]:
            if rule.get("id") == rule_id:
                rule["last_fired"] = datetime.now(local_tz).isoformat()
                save_rules(data, config)
                return


def load_triggered(config: Config) -> dict[str, str]:
    """Load triggered events log.

    Note: This is NOT thread-safe. Use with _rules_lock for concurrent access.
    """
    if not config.triggered_file.exists():
        return {}
    try:
        with open(config.triggered_file, "r") as f:
            data = json.load(f)
        # Validate structure
        if not isinstance(data, dict):
            print(f"Warning: Triggered file has invalid structure (expected dict), returning empty")
            return {}
        return data
    except json.JSONDecodeError as e:
        print(f"Warning: Triggered file has invalid JSON: {e}")
        return {}
    except OSError as e:
        print(f"Warning: Cannot read triggered file: {e}")
        return {}


def save_triggered(data: dict[str, str], config: Config) -> None:
    """Save triggered events log atomically."""
    atomic_write_json(data, config.triggered_file)


def mark_event_triggered(rule_id: str, event_id: str, config: Config) -> None:
    """Mark a rule+event combination as triggered.

    Uses timezone-aware timestamp for consistency with other timestamps.
    """
    with _rules_lock:
        triggered = load_triggered(config)
        key = f"{rule_id}:{event_id}"
        local_tz = ZoneInfo(config.timezone)
        triggered[key] = datetime.now(local_tz).isoformat()
        save_triggered(triggered, config)


def is_event_triggered(rule_id: str, event_id: str, config: Config) -> bool:
    """Check if a rule+event combination has already been triggered.

    Thread-safe: acquires lock to prevent reading while another thread writes.
    """
    with _rules_lock:
        triggered = load_triggered(config)
        key = f"{rule_id}:{event_id}"
        return key in triggered


def cleanup_old_triggered(config: Config, max_age_days: int = 90) -> int:
    """Remove triggered event entries older than max_age_days.

    Returns the number of entries removed.

    This should be called periodically (e.g., weekly) to prevent unbounded
    growth of the triggered events file.
    """
    with _rules_lock:
        triggered = load_triggered(config)
        if not triggered:
            return 0

        local_tz = ZoneInfo(config.timezone)
        now = datetime.now(local_tz)
        cutoff = now - timedelta(days=max_age_days)

        to_remove = []
        for key, timestamp_str in triggered.items():
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                # Handle both timezone-aware and naive timestamps
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=local_tz)
                if timestamp < cutoff:
                    to_remove.append(key)
            except (ValueError, TypeError):
                # Invalid timestamp, remove it
                to_remove.append(key)

        if to_remove:
            for key in to_remove:
                del triggered[key]
            save_triggered(triggered, config)

        return len(to_remove)
