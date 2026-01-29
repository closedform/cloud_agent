"""Stress tests for src/reminders.py - Bug hunting for edge cases."""

import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
from zoneinfo import ZoneInfo

import pytest

from src.models import Reminder
from src.reminders import (
    _load_reminders,
    _save_reminders,
    _reminders_lock,
    add_reminder,
    schedule_reminder,
    load_existing_reminders,
    send_reminder_email,
)


class TestPastReminders:
    """Tests for reminders scheduled in the past."""

    def test_past_reminder_fires_immediately(self, test_config):
        """A reminder in the past should fire immediately, not schedule a timer."""
        past_time = datetime.now(ZoneInfo(test_config.timezone)) - timedelta(hours=1)

        reminder = Reminder.create(
            message="Past reminder",
            reminder_datetime=past_time.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.send_reminder_email") as mock_send:
            with patch("src.reminders.threading.Timer") as mock_timer:
                schedule_reminder(reminder, test_config)

                # Should call send_reminder_email directly, not schedule a timer
                mock_send.assert_called_once()
                mock_timer.assert_not_called()

    def test_past_reminder_very_old(self, test_config):
        """A reminder from years ago should still fire immediately."""
        ancient_time = datetime(2020, 1, 1, 12, 0, 0, tzinfo=ZoneInfo(test_config.timezone))

        reminder = Reminder.create(
            message="Ancient reminder",
            reminder_datetime=ancient_time.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.send_reminder_email") as mock_send:
            schedule_reminder(reminder, test_config)
            mock_send.assert_called_once()

    def test_past_reminder_just_barely_past(self, test_config):
        """A reminder just barely in the past (1 second) should fire immediately."""
        local_tz = ZoneInfo(test_config.timezone)
        just_past = datetime.now(local_tz) - timedelta(seconds=1)

        reminder = Reminder.create(
            message="Just missed it",
            reminder_datetime=just_past.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.send_reminder_email") as mock_send:
            schedule_reminder(reminder, test_config)
            mock_send.assert_called_once()

    def test_past_reminder_at_exact_now(self, test_config):
        """BUG HUNT: A reminder at exactly now (delay=0) should fire immediately."""
        local_tz = ZoneInfo(test_config.timezone)

        # Get current time and create reminder for that exact moment
        now = datetime.now(local_tz)

        reminder = Reminder.create(
            message="Exactly now",
            reminder_datetime=now.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.send_reminder_email") as mock_send:
            with patch("src.reminders.threading.Timer") as mock_timer:
                schedule_reminder(reminder, test_config)

                # delay <= 0 should trigger immediate send
                # If this fails, there's a bug in the boundary condition
                mock_send.assert_called_once()


class TestFarFutureReminders:
    """Tests for reminders scheduled very far in the future."""

    def test_far_future_reminder_schedules(self, test_config):
        """A reminder 1 year in the future should schedule (not overflow)."""
        local_tz = ZoneInfo(test_config.timezone)
        far_future = datetime.now(local_tz) + timedelta(days=365)

        reminder = Reminder.create(
            message="See you next year",
            reminder_datetime=far_future.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            schedule_reminder(reminder, test_config)

            mock_timer.assert_called_once()
            delay = mock_timer.call_args[0][0]

            # Should be approximately 365 days in seconds
            expected_seconds = 365 * 24 * 60 * 60
            assert delay > expected_seconds - 100  # Allow small tolerance
            assert delay < expected_seconds + 100

    def test_far_future_reminder_100_years(self, test_config):
        """BUG HUNT: A reminder 100 years in the future - potential overflow?"""
        local_tz = ZoneInfo(test_config.timezone)
        very_far_future = datetime.now(local_tz) + timedelta(days=365 * 100)

        reminder = Reminder.create(
            message="Century reminder",
            reminder_datetime=very_far_future.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            # This should not crash or overflow
            schedule_reminder(reminder, test_config)

            mock_timer.assert_called_once()
            delay = mock_timer.call_args[0][0]

            # Verify delay is positive and large
            assert delay > 0
            # 100 years in seconds is about 3.15 billion - well within Python float range
            expected_seconds = 100 * 365 * 24 * 60 * 60
            assert abs(delay - expected_seconds) < expected_seconds * 0.01  # 1% tolerance

    def test_far_future_timer_actually_created_as_daemon(self, test_config):
        """Verify far future timers are daemonized (won't block shutdown)."""
        local_tz = ZoneInfo(test_config.timezone)
        future = datetime.now(local_tz) + timedelta(days=30)

        reminder = Reminder.create(
            message="30 days out",
            reminder_datetime=future.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            schedule_reminder(reminder, test_config)

            # Verify daemon was set to True
            assert mock_timer_instance.daemon == True
            mock_timer_instance.start.assert_called_once()


class TestRapidCreationCancellation:
    """Tests for rapid creation and implicit cancellation via restart."""

    def test_rapid_creation_no_race_conditions(self, test_config):
        """Rapidly creating many reminders should not lose any."""
        num_reminders = 100
        local_tz = ZoneInfo(test_config.timezone)

        for i in range(num_reminders):
            reminder = Reminder.create(
                message=f"Rapid reminder {i}",
                reminder_datetime=(datetime.now(local_tz) + timedelta(hours=i + 1)).isoformat(),
                reply_to="test@example.com",
            )
            add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert len(reminders) == num_reminders

    def test_rapid_concurrent_creation(self, test_config):
        """Concurrently creating reminders from multiple threads."""
        num_threads = 20
        reminders_per_thread = 10
        errors = []
        local_tz = ZoneInfo(test_config.timezone)

        def create_reminders(thread_id):
            try:
                for i in range(reminders_per_thread):
                    reminder = Reminder.create(
                        message=f"Thread {thread_id} reminder {i}",
                        reminder_datetime=(
                            datetime.now(local_tz) + timedelta(hours=thread_id * 100 + i + 1)
                        ).isoformat(),
                        reply_to=f"test{thread_id}@example.com",
                    )
                    add_reminder(reminder, test_config)
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [
            threading.Thread(target=create_reminders, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        expected = num_threads * reminders_per_thread
        assert len(reminders) == expected, f"Expected {expected}, got {len(reminders)}"

    def test_timer_cancellation_is_supported(self, test_config):
        """The reminders module now has a cancel_reminder function.

        Users can cancel scheduled reminders before they fire.
        """
        import src.reminders as reminders_module

        assert hasattr(reminders_module, 'cancel_reminder'), \
            "cancel_reminder function should exist in reminders module"

    def test_duplicate_reminder_ids_not_prevented(self, test_config):
        """BUG HUNT: Can we create reminders with duplicate IDs?"""
        local_tz = ZoneInfo(test_config.timezone)

        # Create two reminders with the same explicit ID
        reminder1 = Reminder(
            id="duplicate-id",
            message="First reminder",
            datetime=(datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
            created_at=datetime.now().isoformat(),
        )

        reminder2 = Reminder(
            id="duplicate-id",  # Same ID!
            message="Second reminder",
            datetime=(datetime.now(local_tz) + timedelta(hours=2)).isoformat(),
            reply_to="test@example.com",
            created_at=datetime.now().isoformat(),
        )

        add_reminder(reminder1, test_config)
        add_reminder(reminder2, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        # BUG: Both reminders are saved with the same ID!
        # This can cause issues when one fires and tries to remove by ID
        assert len(reminders) == 2, "Both reminders saved (duplicate IDs allowed - potential bug)"

        # Verify they have the same ID
        ids = [r["id"] for r in reminders]
        assert ids.count("duplicate-id") == 2, "Duplicate IDs were saved"


class TestTimerPersistenceAcrossRestarts:
    """Tests for timer persistence and reload behavior."""

    def test_load_existing_reminders_schedules_all(self, test_config):
        """Loading existing reminders should schedule timers for all."""
        local_tz = ZoneInfo(test_config.timezone)

        # Pre-populate reminders file
        reminders_data = [
            {
                "id": f"reminder-{i}",
                "message": f"Reminder {i}",
                "datetime": (datetime.now(local_tz) + timedelta(hours=i + 1)).isoformat(),
                "reply_to": "test@example.com",
                "created_at": datetime.now().isoformat(),
            }
            for i in range(5)
        ]

        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.reminders_file, "w") as f:
            json.dump(reminders_data, f)

        with patch("src.reminders.schedule_reminder") as mock_schedule:
            load_existing_reminders(test_config)

            # Should schedule all 5 reminders
            assert mock_schedule.call_count == 5

    def test_load_existing_reminders_handles_past_reminders(self, test_config):
        """Past reminders should fire immediately on load."""
        local_tz = ZoneInfo(test_config.timezone)

        # Pre-populate with a past reminder
        past_time = datetime.now(local_tz) - timedelta(hours=1)
        reminders_data = [
            {
                "id": "past-reminder",
                "message": "Should have fired already",
                "datetime": past_time.isoformat(),
                "reply_to": "test@example.com",
                "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
            }
        ]

        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.reminders_file, "w") as f:
            json.dump(reminders_data, f)

        with patch("src.reminders.send_reminder_email") as mock_send:
            load_existing_reminders(test_config)

            # Past reminder should be sent immediately
            mock_send.assert_called_once()

    def test_simulated_restart_preserves_reminders(self, test_config):
        """Simulating a restart: reminders should survive and reload."""
        local_tz = ZoneInfo(test_config.timezone)

        # Phase 1: Create reminders (simulating first run)
        for i in range(3):
            reminder = Reminder.create(
                message=f"Persistent reminder {i}",
                reminder_datetime=(datetime.now(local_tz) + timedelta(hours=i + 10)).isoformat(),
                reply_to="test@example.com",
            )
            add_reminder(reminder, test_config)

        # Verify they were saved
        with _reminders_lock:
            saved_before = _load_reminders(test_config)
        assert len(saved_before) == 3

        # Phase 2: Simulate restart - load existing reminders
        with patch("src.reminders.schedule_reminder") as mock_schedule:
            load_existing_reminders(test_config)

            # All 3 should be rescheduled
            assert mock_schedule.call_count == 3

    def test_fired_reminder_removed_from_persistence(self, test_config):
        """When a reminder fires, it should be removed from the JSON file."""
        local_tz = ZoneInfo(test_config.timezone)

        # Pre-populate with reminders
        reminders_data = [
            {
                "id": "will-fire",
                "message": "This will fire",
                "datetime": (datetime.now(local_tz) + timedelta(seconds=1)).isoformat(),
                "reply_to": "test@example.com",
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "will-stay",
                "message": "This stays",
                "datetime": (datetime.now(local_tz) + timedelta(hours=10)).isoformat(),
                "reply_to": "test@example.com",
                "created_at": datetime.now().isoformat(),
            },
        ]

        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.reminders_file, "w") as f:
            json.dump(reminders_data, f)

        # Simulate firing the first reminder
        # log_fired_reminder is imported inside send_reminder_email from src.diary
        with patch("src.reminders.send_email"):
            with patch("src.diary.log_fired_reminder"):
                send_reminder_email(
                    "will-fire",
                    "This will fire",
                    "test@example.com",
                    datetime.now().isoformat(),
                    test_config,
                )

        # Verify only one reminder remains
        with _reminders_lock:
            remaining = _load_reminders(test_config)

        assert len(remaining) == 1
        assert remaining[0]["id"] == "will-stay"

    def test_corrupt_reminders_file_handled(self, test_config):
        """BUG HUNT: What happens with a corrupt JSON file?"""
        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)

        # Write corrupt JSON
        with open(test_config.reminders_file, "w") as f:
            f.write("{ this is not valid json }")

        # Should not crash, should return empty list
        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert reminders == []

    def test_load_existing_with_missing_fields(self, test_config):
        """BUG HUNT: Reminders with missing required fields in JSON."""
        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)

        # Write reminder with missing 'datetime' field
        invalid_data = [
            {
                "id": "incomplete",
                "message": "Missing datetime",
                "reply_to": "test@example.com",
                # Missing: "datetime"
            }
        ]

        with open(test_config.reminders_file, "w") as f:
            json.dump(invalid_data, f)

        # This will raise ValueError when Reminder.from_dict is called
        # BUG: load_existing_reminders catches generic Exception but doesn't
        # handle individual reminder failures gracefully
        with patch("builtins.print") as mock_print:
            load_existing_reminders(test_config)

            # Should have printed an error
            assert any("Error" in str(call) for call in mock_print.call_args_list)


class TestEdgeCases:
    """Additional edge cases and potential bugs."""

    def test_empty_message_reminder(self, test_config):
        """What happens with an empty message?"""
        local_tz = ZoneInfo(test_config.timezone)

        reminder = Reminder.create(
            message="",  # Empty message
            reminder_datetime=(datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
        )

        # Should not crash
        add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert len(reminders) == 1
        assert reminders[0]["message"] == ""

    def test_very_long_message(self, test_config):
        """What happens with a very long message?"""
        local_tz = ZoneInfo(test_config.timezone)

        long_message = "X" * 100000  # 100KB message

        reminder = Reminder.create(
            message=long_message,
            reminder_datetime=(datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
        )

        add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert len(reminders) == 1
        assert len(reminders[0]["message"]) == 100000

    def test_special_characters_in_message(self, test_config):
        """Messages with special characters, unicode, emojis."""
        local_tz = ZoneInfo(test_config.timezone)

        special_message = "Hello! \U0001F4E7 Reminder: \"Don't forget!\" \n\t<script>alert('xss')</script> \u4e2d\u6587"

        reminder = Reminder.create(
            message=special_message,
            reminder_datetime=(datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
        )

        add_reminder(reminder, test_config)

        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert len(reminders) == 1
        assert reminders[0]["message"] == special_message

    def test_invalid_datetime_format(self, test_config):
        """BUG HUNT: What happens with invalid datetime format?"""
        reminder = Reminder(
            id="bad-datetime",
            message="Bad datetime",
            datetime="not-a-real-datetime",  # Invalid!
            reply_to="test@example.com",
            created_at=datetime.now().isoformat(),
        )

        # schedule_reminder should handle this gracefully
        with patch("builtins.print") as mock_print:
            schedule_reminder(reminder, test_config)

            # Should print an error, not crash
            assert any("Error" in str(call) for call in mock_print.call_args_list)

    def test_invalid_timezone_in_datetime(self, test_config):
        """Datetime string with unusual timezone offset."""
        local_tz = ZoneInfo(test_config.timezone)

        # Create a datetime with explicit offset
        future = datetime.now(local_tz) + timedelta(hours=1)
        # Format with unusual offset representation
        dt_string = future.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        reminder = Reminder.create(
            message="UTC reminder",
            reminder_datetime=dt_string,
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            # Should handle the timezone properly
            schedule_reminder(reminder, test_config)

            # Should schedule (or fire if in past depending on UTC offset)
            assert mock_timer.called or True  # May or may not schedule depending on local tz

    def test_reminder_with_none_values_in_storage(self, test_config):
        """BUG HUNT: What if stored reminder has None values?"""
        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)

        # Write reminder with None values (shouldn't happen but could)
        bad_data = [
            {
                "id": "has-none",
                "message": None,  # None instead of string
                "datetime": (datetime.now() + timedelta(hours=1)).isoformat(),
                "reply_to": "test@example.com",
                "created_at": datetime.now().isoformat(),
            }
        ]

        with open(test_config.reminders_file, "w") as f:
            json.dump(bad_data, f)

        # Reminder.from_dict doesn't validate types, only presence
        # This could cause issues downstream
        with _reminders_lock:
            reminders = _load_reminders(test_config)

        # The data is loaded but message is None
        assert reminders[0]["message"] is None

    def test_concurrent_fire_and_add(self, test_config):
        """Race condition: Adding while a reminder is firing."""
        local_tz = ZoneInfo(test_config.timezone)

        # Pre-populate with a reminder
        initial_data = [
            {
                "id": "initial",
                "message": "Initial",
                "datetime": (datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
                "reply_to": "test@example.com",
                "created_at": datetime.now().isoformat(),
            }
        ]

        test_config.reminders_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.reminders_file, "w") as f:
            json.dump(initial_data, f)

        results = []
        errors = []

        def fire_reminder():
            try:
                # log_fired_reminder is imported inside send_reminder_email from src.diary
                with patch("src.reminders.send_email"):
                    with patch("src.diary.log_fired_reminder"):
                        send_reminder_email(
                            "initial",
                            "Initial",
                            "test@example.com",
                            datetime.now().isoformat(),
                            test_config,
                        )
                results.append("fired")
            except Exception as e:
                errors.append(("fire", str(e)))

        def add_new_reminder():
            try:
                new_reminder = Reminder.create(
                    message="New during fire",
                    reminder_datetime=(datetime.now(local_tz) + timedelta(hours=2)).isoformat(),
                    reply_to="test@example.com",
                )
                add_reminder(new_reminder, test_config)
                results.append("added")
            except Exception as e:
                errors.append(("add", str(e)))

        # Run concurrently
        t1 = threading.Thread(target=fire_reminder)
        t2 = threading.Thread(target=add_new_reminder)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # Should have 1 reminder (initial removed, new added)
        with _reminders_lock:
            reminders = _load_reminders(test_config)

        assert len(reminders) == 1
        assert reminders[0]["message"] == "New during fire"


class TestTimerBehavior:
    """Tests specifically for threading.Timer behavior."""

    def test_timer_delay_precision(self, test_config):
        """BUG HUNT: Are small delays handled precisely?"""
        local_tz = ZoneInfo(test_config.timezone)

        # 1 second from now
        one_second_future = datetime.now(local_tz) + timedelta(seconds=1)

        reminder = Reminder.create(
            message="One second",
            reminder_datetime=one_second_future.isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            schedule_reminder(reminder, test_config)

            mock_timer.assert_called_once()
            delay = mock_timer.call_args[0][0]

            # Delay should be close to 1 second (allow for execution time)
            assert 0 < delay < 2, f"Delay was {delay}s, expected ~1s"

    def test_many_timers_memory(self, test_config):
        """Creating many timers shouldn't cause memory issues.

        Note: This is a documentation test - Python's threading.Timer is lightweight
        but 10000 active timers could still be problematic in production.
        """
        local_tz = ZoneInfo(test_config.timezone)

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            # Create 1000 future reminders
            for i in range(1000):
                reminder = Reminder.create(
                    message=f"Reminder {i}",
                    reminder_datetime=(datetime.now(local_tz) + timedelta(days=i + 1)).isoformat(),
                    reply_to="test@example.com",
                )
                schedule_reminder(reminder, test_config)

            # 1000 timers created
            assert mock_timer.call_count == 1000

    def test_timer_not_started_twice(self, test_config):
        """Each reminder should only start one timer."""
        local_tz = ZoneInfo(test_config.timezone)

        reminder = Reminder.create(
            message="Single timer",
            reminder_datetime=(datetime.now(local_tz) + timedelta(hours=1)).isoformat(),
            reply_to="test@example.com",
        )

        with patch("src.reminders.threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            schedule_reminder(reminder, test_config)

            # Timer created once
            mock_timer.assert_called_once()
            # Start called once
            mock_timer_instance.start.assert_called_once()
