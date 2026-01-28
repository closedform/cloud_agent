"""Rule storage and CRUD operations.

Rules define automated actions triggered by time (cron) or calendar events.
"""

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.config import Config

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
        """Create a time-based rule with cron schedule."""
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
    """Load all rules from file, returning empty dict if not found."""
    if not config.rules_file.exists():
        return {}
    try:
        with open(config.rules_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_rules(data: dict[str, list[dict[str, Any]]], config: Config) -> None:
    """Save rules atomically using temp file + rename."""
    dir_path = config.rules_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, config.rules_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_user_rules(email: str, config: Config) -> list[Rule]:
    """Get all rules for a user."""
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
    """Load triggered events log."""
    if not config.triggered_file.exists():
        return {}
    try:
        with open(config.triggered_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_triggered(data: dict[str, str], config: Config) -> None:
    """Save triggered events log atomically."""
    dir_path = config.triggered_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, config.triggered_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def mark_event_triggered(rule_id: str, event_id: str, config: Config) -> None:
    """Mark a rule+event combination as triggered."""
    with _rules_lock:
        triggered = load_triggered(config)
        key = f"{rule_id}:{event_id}"
        triggered[key] = datetime.now().isoformat()
        save_triggered(triggered, config)


def is_event_triggered(rule_id: str, event_id: str, config: Config) -> bool:
    """Check if a rule+event combination has already been triggered."""
    triggered = load_triggered(config)
    key = f"{rule_id}:{event_id}"
    return key in triggered
