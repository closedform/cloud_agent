"""Reminder scheduling and persistence.

Handles scheduling reminders using threading.Timer and persisting to JSON.
"""

import json
import os
import tempfile
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from src.clients.email import send_email, html_reminder
from src.config import Config
from src.models import Reminder

# Lock for atomic reminder file operations
_reminders_lock = threading.Lock()


def _load_reminders(config: Config) -> list[dict]:
    """Load reminders from file (must be called with lock held)."""
    if not config.reminders_file.exists():
        return []
    try:
        with open(config.reminders_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_reminders(reminders: list[dict], config: Config) -> None:
    """Save reminders atomically using temp file + rename (must be called with lock held)."""
    dir_path = config.reminders_file.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(reminders, f, indent=2)
        os.rename(tmp_path, config.reminders_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def send_reminder_email(
    reminder_id: str,
    message: str,
    reply_to: str,
    created_at: str,
    config: Config,
) -> None:
    """Send a reminder email and remove it from storage."""
    try:
        # Log the reminder for diary aggregation
        from src.diary import log_fired_reminder

        log_fired_reminder(reply_to, message, config)

        plain_body = f"This is your reminder: {message}\n\nOriginally set: {created_at}"
        html_body = html_reminder(message, created_at)

        send_email(
            to_address=reply_to,
            subject=f"⏰ {message}",
            body=plain_body,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            html_body=html_body,
        )
        print(f"Reminder fired: {message[:30]}... -> {reply_to}")

        # Remove from reminders.json atomically with locking
        with _reminders_lock:
            reminders = _load_reminders(config)
            reminders = [r for r in reminders if r.get("id") != reminder_id]
            _save_reminders(reminders, config)

    except Exception as e:
        print(f"Error sending reminder: {e}")


def schedule_reminder(reminder: Reminder, config: Config) -> None:
    """Schedule a reminder using threading.Timer.

    Handles both timezone-aware and naive datetime strings.
    """
    try:
        reminder_time = datetime.fromisoformat(reminder.datetime)
        local_tz = ZoneInfo(config.timezone)

        # Ensure both times are timezone-aware for comparison
        if reminder_time.tzinfo is None:
            reminder_time = reminder_time.replace(tzinfo=local_tz)
        now = datetime.now(local_tz)
        delay = (reminder_time - now).total_seconds()

        if delay <= 0:
            # Already past due, send immediately
            send_reminder_email(
                reminder.id,
                reminder.message,
                reminder.reply_to,
                reminder.created_at,
                config,
            )
        else:
            # Schedule for later
            timer = threading.Timer(
                delay,
                send_reminder_email,
                args=[
                    reminder.id,
                    reminder.message,
                    reminder.reply_to,
                    reminder.created_at,
                    config,
                ],
            )
            timer.daemon = True
            timer.start()
            print(f"  Scheduled reminder in {delay:.0f}s: {reminder.message[:30]}...")

    except Exception as e:
        print(f"Error scheduling reminder: {e}")


def add_reminder(reminder: Reminder, config: Config) -> None:
    """Add a reminder to storage and schedule it.

    Uses atomic file operations with locking to prevent race conditions.
    The entire read-modify-write cycle is protected by the lock.

    Args:
        reminder: Reminder to add.
        config: Application configuration.
    """
    # Add to storage atomically - lock covers entire read-modify-write cycle
    with _reminders_lock:
        reminders = _load_reminders(config)
        reminders.append(reminder.to_dict())
        _save_reminders(reminders, config)

    # Schedule the reminder (outside lock to avoid blocking)
    schedule_reminder(reminder, config)


def load_existing_reminders(config: Config) -> None:
    """Load and schedule any existing reminders from file."""
    if not config.reminders_file.exists():
        return

    try:
        with _reminders_lock:
            reminders_data = _load_reminders(config)

        if reminders_data:
            print(f"Loading {len(reminders_data)} existing reminder(s)...")
            for reminder_dict in reminders_data:
                reminder = Reminder.from_dict(reminder_dict)
                schedule_reminder(reminder, config)

    except Exception as e:
        print(f"Error loading reminders: {e}")
