"""Reminder scheduling and persistence.

Handles scheduling reminders using threading.Timer and persisting to JSON.
"""

import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from src.clients.email import send_email, html_reminder
from src.config import Config
from src.models import Reminder
from src.utils import atomic_write_json

# Lock for atomic reminder file operations
_reminders_lock = threading.Lock()

# Track active timers for cancellation support
# Maps reminder_id -> Timer object
_active_timers: dict[str, threading.Timer] = {}
_timers_lock = threading.Lock()


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
    """Save reminders atomically (must be called with lock held)."""
    atomic_write_json(reminders, config.reminders_file)


def send_reminder_email(
    reminder_id: str,
    message: str,
    reply_to: str,
    created_at: str,
    config: Config,
) -> None:
    """Send a reminder email and remove it from storage.

    Security: Validates reply_to against allowed_senders whitelist.

    This function is called from threading.Timer callbacks, so all exceptions
    must be caught to prevent silent thread death.
    """
    email_sent = False
    try:
        # Security: Validate recipient against allowed senders whitelist
        allowed_senders_lower = {s.lower() for s in config.allowed_senders}
        if reply_to.lower() not in allowed_senders_lower:
            print(f"Security: Blocked reminder to non-whitelisted recipient: {reply_to}")
            # email_sent stays False, cleanup will happen in finally block
            return

        # Log the reminder for diary aggregation
        from src.diary import log_fired_reminder

        try:
            log_fired_reminder(reply_to, message, config)
        except Exception as e:
            # Don't fail the reminder if logging fails
            print(f"Warning: Failed to log reminder for diary: {e}")

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
        email_sent = True
        print(f"Reminder fired: {message[:30]}... -> {reply_to}")

    except Exception as e:
        print(f"Error sending reminder email: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always clean up storage and timer tracking, even if email failed
        # This prevents reminder from being "stuck" and retried forever on restart
        try:
            with _reminders_lock:
                reminders = _load_reminders(config)
                reminders = [r for r in reminders if r.get("id") != reminder_id]
                _save_reminders(reminders, config)
        except Exception as e:
            print(f"Error cleaning up reminder {reminder_id} from storage: {e}")

        # Clean up timer from tracking dict
        with _timers_lock:
            _active_timers.pop(reminder_id, None)


def schedule_reminder(reminder: Reminder, config: Config) -> None:
    """Schedule a reminder using threading.Timer.

    Handles both timezone-aware and naive datetime strings.
    Tracks the timer for potential cancellation.
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

            # Track timer for potential cancellation
            with _timers_lock:
                # Cancel any existing timer for this reminder ID (prevents duplicates on reload)
                old_timer = _active_timers.pop(reminder.id, None)
                if old_timer is not None:
                    old_timer.cancel()
                _active_timers[reminder.id] = timer

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


def cancel_reminder(reminder_id: str, config: Config) -> bool:
    """Cancel a scheduled reminder by ID.

    Removes the reminder from both the timer tracking and persistent storage.

    Args:
        reminder_id: ID of the reminder to cancel.
        config: Application configuration.

    Returns:
        True if the reminder was found and cancelled, False otherwise.
    """
    cancelled = False

    # Cancel the timer if active
    with _timers_lock:
        timer = _active_timers.pop(reminder_id, None)
        if timer is not None:
            timer.cancel()
            cancelled = True

    # Remove from persistent storage
    with _reminders_lock:
        reminders = _load_reminders(config)
        original_count = len(reminders)
        reminders = [r for r in reminders if r.get("id") != reminder_id]
        if len(reminders) < original_count:
            _save_reminders(reminders, config)
            cancelled = True

    return cancelled


def cancel_all_reminders() -> int:
    """Cancel all active reminder timers.

    Useful for graceful shutdown. Does not modify persistent storage,
    so reminders will be rescheduled on next startup.

    Returns:
        Number of timers cancelled.
    """
    with _timers_lock:
        count = len(_active_timers)
        for timer in _active_timers.values():
            timer.cancel()
        _active_timers.clear()
    return count


def get_active_reminder_count() -> int:
    """Get the number of currently scheduled reminders.

    Returns:
        Number of active reminder timers.
    """
    with _timers_lock:
        return len(_active_timers)
