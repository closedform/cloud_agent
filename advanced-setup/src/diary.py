"""Diary storage and generation.

Generates weekly diary entries from user activity (todos, reminders, calendar).
"""

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.config import Config

# Lock for thread-safe file operations
_diary_lock = threading.Lock()


@dataclass
class DiaryEntry:
    """Represents a weekly diary entry."""

    id: str  # Format: "2026-W04"
    user_email: str
    week_start: str  # ISO date
    week_end: str  # ISO date
    content: str
    sources: dict[str, list[str]] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "user_email": self.user_email,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "content": self.content,
            "sources": self.sources,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiaryEntry":
        """Create DiaryEntry from dictionary."""
        return cls(
            id=data["id"],
            user_email=data["user_email"],
            week_start=data["week_start"],
            week_end=data["week_end"],
            content=data["content"],
            sources=data.get("sources", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


def get_week_id(date: datetime | None = None, tz: str | None = None) -> str:
    """Get ISO week ID for a date (e.g., '2026-W04').

    Uses isocalendar() for both year and week to handle year boundaries correctly.
    E.g., Dec 29 might be ISO week 1 of the next year.

    Args:
        date: Date to get week ID for. Defaults to now.
        tz: Timezone name (e.g., 'America/New_York'). If provided, uses timezone-aware now.
    """
    if date is None:
        if tz:
            date = datetime.now(ZoneInfo(tz))
        else:
            date = datetime.now()
    iso_year, iso_week, _ = date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def get_week_bounds(
    date: datetime | None = None, tz: str | None = None
) -> tuple[datetime, datetime]:
    """Get the start (Monday) and end (Sunday) of the week containing the date.

    Args:
        date: Date to get week bounds for. Defaults to now.
        tz: Timezone name (e.g., 'America/New_York'). If provided, returns timezone-aware datetimes.

    Returns:
        Tuple of (monday 00:00:00, sunday 23:59:59) for the week.
    """
    if date is None:
        if tz:
            date = datetime.now(ZoneInfo(tz))
        else:
            date = datetime.now()
    # Find Monday of this week
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def load_diary(config: Config) -> dict[str, list[dict[str, Any]]]:
    """Load all diary entries from file."""
    if not config.diary_file.exists():
        return {}
    try:
        with open(config.diary_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_diary(data: dict[str, list[dict[str, Any]]], config: Config) -> None:
    """Save diary entries atomically."""
    dir_path = config.diary_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, config.diary_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_user_diary_entries(
    email: str, config: Config, limit: int | None = None
) -> list[DiaryEntry]:
    """Get diary entries for a user, most recent first."""
    data = load_diary(config)
    entries_data = data.get(email, [])
    entries = [DiaryEntry.from_dict(e) for e in entries_data]
    # Sort by week_start descending
    entries.sort(key=lambda e: e.week_start, reverse=True)
    if limit:
        entries = entries[:limit]
    return entries


def get_diary_entry(email: str, week_id: str, config: Config) -> DiaryEntry | None:
    """Get a specific diary entry by week ID."""
    data = load_diary(config)
    entries_data = data.get(email, [])
    for entry_data in entries_data:
        if entry_data.get("id") == week_id:
            return DiaryEntry.from_dict(entry_data)
    return None


def save_diary_entry(entry: DiaryEntry, config: Config) -> None:
    """Save or update a diary entry."""
    with _diary_lock:
        data = load_diary(config)
        if entry.user_email not in data:
            data[entry.user_email] = []

        # Check if entry for this week already exists
        entries = data[entry.user_email]
        for i, existing in enumerate(entries):
            if existing.get("id") == entry.id:
                entries[i] = entry.to_dict()
                save_diary(data, config)
                return

        # Add new entry
        entries.append(entry.to_dict())
        save_diary(data, config)


def load_reminder_log(config: Config) -> list[dict[str, Any]]:
    """Load reminder log entries."""
    if not config.reminder_log_file.exists():
        return []
    try:
        with open(config.reminder_log_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_reminder_log(data: list[dict[str, Any]], config: Config) -> None:
    """Save reminder log atomically."""
    dir_path = config.reminder_log_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, config.reminder_log_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def log_fired_reminder(
    user_email: str, message: str, config: Config
) -> None:
    """Log a fired reminder for diary aggregation."""
    local_tz = ZoneInfo(config.timezone)
    with _diary_lock:
        log = load_reminder_log(config)
        log.append({
            "user": user_email,
            "message": message,
            "fired_at": datetime.now(local_tz).isoformat(),
        })
        save_reminder_log(log, config)


def get_reminders_in_range(
    email: str, start: datetime, end: datetime, config: Config
) -> list[str]:
    """Get reminder messages fired within a date range for a user.

    Handles both timezone-aware and naive fired_at timestamps.
    If start/end are tz-aware and fired_at is naive, assumes local timezone.
    """
    local_tz = ZoneInfo(config.timezone)
    log = load_reminder_log(config)
    messages = []
    for entry in log:
        if entry.get("user") != email:
            continue
        fired_at_str = entry.get("fired_at")
        if not fired_at_str:
            continue
        try:
            fired_at = datetime.fromisoformat(fired_at_str)
            # Ensure timezone consistency for comparison
            if start.tzinfo is not None and fired_at.tzinfo is None:
                fired_at = fired_at.replace(tzinfo=local_tz)
            elif start.tzinfo is None and fired_at.tzinfo is not None:
                fired_at = fired_at.replace(tzinfo=None)
        except ValueError:
            continue
        if start <= fired_at <= end:
            messages.append(entry.get("message", ""))
    return messages
