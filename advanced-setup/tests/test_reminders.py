"""Tests for src/reminders.py"""

import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.models import Reminder
from src.reminders import (
    _load_reminders,
    _save_reminders,
    add_reminder,
    _reminders_lock,
)


class TestReminderAtomicOperations:
    """Tests for atomic reminder file operations."""

    def test_save_creates_file(self, test_config):
        """Should create reminders file if it doesn't exist."""
        reminders = [{"id": "r1", "message": "Test"}]
        with _reminders_lock:
            _save_reminders(reminders, test_config)

        assert test_config.reminders_file.exists()

    def test_save_no_temp_files_remain(self, test_config):
        """Should not leave temporary files after save."""
        reminders = [{"id": "r1", "message": "Test"}]
        with _reminders_lock:
            _save_reminders(reminders, test_config)

        tmp_files = list(test_config.reminders_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_load_returns_empty_list_if_no_file(self, test_config):
        """Should return empty list if file doesn't exist."""
        with _reminders_lock:
            result = _load_reminders(test_config)
        assert result == []

    def test_save_load_roundtrip(self, test_config):
        """Should preserve data through save/load cycle."""
        original = [
            {"id": "r1", "message": "Reminder 1", "datetime": "2026-01-15T10:00:00"},
            {"id": "r2", "message": "Reminder 2", "datetime": "2026-01-16T14:30:00"},
        ]
        with _reminders_lock:
            _save_reminders(original, test_config)
            loaded = _load_reminders(test_config)

        assert loaded == original


class TestAddReminder:
    """Tests for add_reminder function."""

    def test_adds_reminder_to_storage(self, test_config):
        """Should add reminder to persistent storage."""
        reminder = Reminder.create(
            message="Test reminder",
            reminder_datetime=(datetime.now() + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
        )

        add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)
        assert len(reminders) == 1
        assert reminders[0]["message"] == "Test reminder"

    def test_multiple_reminders_accumulate(self, test_config):
        """Should accumulate multiple reminders."""
        for i in range(3):
            reminder = Reminder.create(
                message=f"Reminder {i}",
                reminder_datetime=(datetime.now() + timedelta(hours=i + 1)).isoformat(),
                reply_to="test@example.com",
            )
            add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)
        assert len(reminders) == 3


class TestReminderConcurrency:
    """Tests for concurrent reminder operations."""

    def test_concurrent_add_no_lost_updates(self, test_config):
        """Concurrent adds should not lose reminders (race condition test)."""
        num_threads = 10
        reminders_per_thread = 5
        results = []
        errors = []

        def add_reminders(thread_id):
            try:
                for i in range(reminders_per_thread):
                    # Use hours=1 as base to ensure all reminders are in the future
                    # (prevents immediate send which would remove them)
                    reminder = Reminder.create(
                        message=f"Thread {thread_id} Reminder {i}",
                        reminder_datetime=(datetime.now() + timedelta(hours=1 + thread_id * 10 + i)).isoformat(),
                        reply_to=f"test{thread_id}@example.com",
                    )
                    add_reminder(reminder, test_config)
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, e))

        # Start all threads
        threads = [
            threading.Thread(target=add_reminders, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all reminders were saved (no lost updates)
        with _reminders_lock:
            reminders = _load_reminders(test_config)

        expected_count = num_threads * reminders_per_thread
        assert len(reminders) == expected_count, (
            f"Expected {expected_count} reminders, got {len(reminders)}. "
            "Some reminders may have been lost due to race condition."
        )


class TestReminderTimezoneHandling:
    """Tests for timezone-aware reminder scheduling."""

    def test_schedule_reminder_with_timezone_offset(self, test_config):
        """Reminder with timezone offset in datetime should schedule correctly.

        This test ensures that:
        1. Reminders with ISO datetime including timezone offset are parsed correctly
        2. The delay calculation works with tz-aware reminder_time vs tz-aware now()
        3. No TypeError is raised during scheduling (the bug this fixes)
        """
        from zoneinfo import ZoneInfo
        from src.reminders import schedule_reminder

        local_tz = ZoneInfo(test_config.timezone)
        # Create a reminder datetime with explicit timezone offset
        future_time = datetime.now(local_tz) + timedelta(hours=2)
        reminder_datetime_with_tz = future_time.isoformat()  # Includes +HH:MM offset

        reminder = Reminder.create(
            message="Timezone-aware reminder test",
            reminder_datetime=reminder_datetime_with_tz,
            reply_to="test@example.com",
        )

        # This should not raise TypeError (the bug before the fix)
        # schedule_reminder computes: (reminder_time - now).total_seconds()
        # Both must be tz-aware or both naive for this to work
        try:
            schedule_reminder(reminder, test_config)
            scheduled = True
        except TypeError as e:
            if "can't subtract offset-naive and offset-aware" in str(e):
                pytest.fail(
                    "schedule_reminder failed with tz-aware datetime - "
                    "this indicates the timezone fix is not working"
                )
            raise

        assert scheduled, "Reminder should schedule without error"

    def test_schedule_reminder_with_naive_datetime(self, test_config):
        """Reminder with naive datetime should also schedule correctly.

        The fix should handle both naive and aware datetimes gracefully.
        """
        from src.reminders import schedule_reminder

        # Create a reminder with naive datetime (no timezone info)
        future_time = datetime.now() + timedelta(hours=2)
        reminder_datetime_naive = future_time.strftime("%Y-%m-%dT%H:%M:%S")

        reminder = Reminder.create(
            message="Naive datetime reminder test",
            reminder_datetime=reminder_datetime_naive,
            reply_to="test@example.com",
        )

        # Should work with naive datetime too (converted to local tz internally)
        try:
            schedule_reminder(reminder, test_config)
            scheduled = True
        except TypeError:
            pytest.fail("schedule_reminder should handle naive datetimes")

        assert scheduled, "Reminder with naive datetime should schedule"

    def test_schedule_reminder_calculates_correct_delay(self, test_config):
        """Verify delay calculation is correct with timezone-aware times."""
        from zoneinfo import ZoneInfo
        from unittest.mock import patch, MagicMock
        from src.reminders import schedule_reminder

        local_tz = ZoneInfo(test_config.timezone)
        # Schedule 1 hour from now
        future_time = datetime.now(local_tz) + timedelta(hours=1)

        reminder = Reminder.create(
            message="Delay test",
            reminder_datetime=future_time.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            schedule_reminder(reminder, test_config)

            # Verify Timer was called
            assert mock_timer.called, "Timer should be created for future reminder"

            # Get the delay argument (first positional arg)
            call_args = mock_timer.call_args
            delay = call_args[0][0]

            # Delay should be approximately 1 hour (3600 seconds), within 5 seconds tolerance
            assert 3595 <= delay <= 3605, f"Delay should be ~3600s, got {delay}s"
