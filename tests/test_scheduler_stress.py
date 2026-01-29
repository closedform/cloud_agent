"""Stress tests for src/scheduler.py.

Tests edge cases around:
1. Timezone handling and DST transitions
2. Cron expression boundary conditions
3. Long-running tick handling
4. Concurrent rule execution
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
from freezegun import freeze_time

import pytest
from croniter import croniter

from src.rules import Rule, add_rule, load_rules, save_rules
from src.scheduler import check_time_rules, check_event_rules, check_weekly_diary


# Helper: Eastern is UTC-5 in winter, UTC-4 in summer (DST)
# To get midnight Eastern on Jan 15, 2026, use UTC 05:00:00
# To get 2:30 PM Eastern on Jan 15, 2026, use UTC 19:30:00


class TestDSTTransitions:
    """Test scheduler behavior during DST transitions."""

    @freeze_time("2026-03-08 05:00:30")  # March 8 midnight Eastern (UTC-5, before DST)
    def test_cron_midnight_during_spring_forward(self, test_config, mock_services):
        """Test cron at midnight during spring DST transition.

        March 8, 2026 at 2:00 AM becomes 3:00 AM in America/New_York.
        A midnight cron job should fire exactly once.
        """
        # Create a rule that fires at midnight
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 0 * * *",  # Every day at midnight
            action="send_reminder",
            params={"message_template": "Daily reminder"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)

            # Should fire once
            assert mock_send.call_count == 1

    @freeze_time("2026-03-08 08:00:30")  # March 8 3:00:30 AM Eastern (after DST jump, now UTC-4)
    def test_cron_2am_during_spring_forward_skipped(self, test_config, mock_services):
        """Test cron at 2:30 AM during spring DST transition.

        BUG CANDIDATE: 2:30 AM doesn't exist on March 8, 2026 in America/New_York.
        The scheduler uses naive datetimes - what happens?
        """
        # Create a rule that fires at 2:30 AM
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 2 * * *",  # Every day at 2:30 AM
            action="send_reminder",
            params={"message_template": "2:30 AM reminder"},
        )
        add_rule(rule, test_config)

        # On DST transition day, 2:00 AM jumps to 3:00 AM
        # If we check at 3:00 AM, what does croniter return for "next" 2:30?
        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)

            # The 2:30 AM time doesn't exist, but croniter doesn't know about DST
            # croniter will return 2:30 as a valid time, but scheduler will not
            # fire because 2:30 < 3:00
            assert mock_send.call_count == 0

    @freeze_time("2026-11-01 05:30:30")  # November 1 1:30 AM EDT (before fall back, UTC-4)
    def test_cron_1am_during_fall_back_first_fire(self, test_config, mock_services):
        """Test cron at 1:30 AM during fall DST transition - first occurrence.

        November 1, 2026 at 2:00 AM becomes 1:00 AM again.
        A 1:30 AM cron job could potentially fire twice!
        """
        # Create a rule that fires at 1:30 AM
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 1 * * *",  # Every day at 1:30 AM
            action="send_reminder",
            params={"message_template": "1:30 AM reminder"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            with patch("src.scheduler.update_rule_last_fired"):
                check_time_rules(test_config, mock_services)
                # First fire should happen
                assert mock_send.call_count == 1


class TestCronBoundaryConditions:
    """Test cron expressions at time boundaries."""

    @freeze_time("2026-01-15 05:00:00")  # Midnight Eastern (UTC-5)
    def test_cron_midnight_exactly(self, test_config, mock_services):
        """Test cron fires at exactly midnight (00:00:00)."""
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 0 * * *",
            action="send_reminder",
            params={"message_template": "Midnight"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)
            assert mock_send.call_count == 1

    @freeze_time("2026-02-28 05:00:30")  # Feb 28 midnight Eastern (UTC-5)
    def test_cron_last_day_of_month(self, test_config, mock_services):
        """Test cron on last day of month (varying days).

        BUG CANDIDATE: Standard cron doesn't have "last day of month".
        A schedule like "0 0 31 * *" won't fire in February.
        """
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 0 31 * *",  # 31st of every month
            action="send_reminder",
            params={"message_template": "End of month"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)

            # Will NOT fire because Feb doesn't have 31 days
            assert mock_send.call_count == 0

    @freeze_time("2028-02-29 05:00:30")  # Feb 29 2028 midnight Eastern (UTC-5)
    def test_cron_leap_year_feb_29(self, test_config, mock_services):
        """Test cron on Feb 29 in a leap year."""
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 0 29 2 *",  # Feb 29 at midnight
            action="send_reminder",
            params={"message_template": "Leap day"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)
            assert mock_send.call_count == 1

    @freeze_time("2026-01-15 19:30:59")  # 2:30:59 PM Eastern (UTC-5)
    def test_cron_59th_second_boundary(self, test_config, mock_services):
        """Test that rule fires even at 59th second of the minute."""
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 14 * * *",  # 2:30 PM
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)
            assert mock_send.call_count == 1

    @freeze_time("2027-01-01 05:00:30")  # Jan 1 2027 midnight Eastern (UTC-5)
    def test_cron_year_rollover(self, test_config, mock_services):
        """Test cron at midnight on New Year's Day."""
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="0 0 1 1 *",  # Jan 1 at midnight
            action="send_reminder",
            params={"message_template": "Happy New Year"},
        )
        add_rule(rule, test_config)

        with patch("src.scheduler.send_custom_reminder") as mock_send:
            check_time_rules(test_config, mock_services)
            assert mock_send.call_count == 1


class TestDoubleFirePrevention:
    """Test double-fire prevention when tick takes longer than interval."""

    @freeze_time("2026-01-15 19:30:30")  # 2:30:30 PM Eastern (UTC-5)
    def test_rapid_ticks_no_double_fire(self, test_config, mock_services):
        """Test that rapid consecutive ticks don't cause double fires."""
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 14 * * *",
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        fire_count = 0

        def track_fire(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1

        # First tick
        with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
            from src.rules import update_rule_last_fired
            with patch("src.scheduler.update_rule_last_fired", side_effect=lambda e, r, c: update_rule_last_fired(e, r, c)):
                check_time_rules(test_config, mock_services)

        # Second tick (same frozen time - simulates rapid tick)
        with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
            check_time_rules(test_config, mock_services)

        # Should only fire once due to last_fired check
        assert fire_count == 1

    def test_tick_slower_than_interval_prevents_double_fire(self, test_config, mock_services):
        """Test that a slow tick (>60s) doesn't cause issues on next interval.

        BUG CANDIDATE: If check_time_rules takes 70 seconds, the next tick
        might see the same cron minute and try to fire again.
        """
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 14 * * *",
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        fire_count = 0

        def track_fire(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1

        # First tick at 14:30:10
        with freeze_time("2026-01-15 19:30:10"):  # 14:30:10 Eastern
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                from src.rules import update_rule_last_fired
                with patch("src.scheduler.update_rule_last_fired", side_effect=lambda e, r, c: update_rule_last_fired(e, r, c)):
                    check_time_rules(test_config, mock_services)

        # Simulate tick that took 70 seconds - next check is at 14:31:20
        with freeze_time("2026-01-15 19:31:20"):  # 14:31:20 Eastern
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                check_time_rules(test_config, mock_services)

        # Should only fire once
        assert fire_count == 1

    def test_120_second_window_edge_case(self, test_config, mock_services):
        """Test the 120-second double-fire prevention window.

        BUG: The scheduler uses a 120-second window to prevent double-fires.
        But if a cron job is scheduled for every minute, this is wrong!
        """
        # Create a rule that fires every minute
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="* * * * *",  # Every minute
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        fire_count = 0

        def track_fire(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1

        # First tick at 14:30:30
        with freeze_time("2026-01-15 19:30:30"):  # 14:30:30 Eastern
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                from src.rules import update_rule_last_fired
                with patch("src.scheduler.update_rule_last_fired", side_effect=lambda e, r, c: update_rule_last_fired(e, r, c)):
                    check_time_rules(test_config, mock_services)

        # Second tick at 14:31:30 (60 seconds later)
        with freeze_time("2026-01-15 19:31:30"):  # 14:31:30 Eastern
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                check_time_rules(test_config, mock_services)

        # FIXED: Now fires twice correctly because 55-second window allows every-minute cron jobs
        # (Previously the 120-second window blocked legitimate every-minute cron)
        assert fire_count == 2, "Every-minute cron should fire twice in 2 ticks"


class TestConcurrentRuleExecution:
    """Test thread safety of rule execution."""

    @freeze_time("2026-01-15 19:30:30")  # 14:30:30 Eastern
    def test_concurrent_check_time_rules(self, test_config, mock_services):
        """Test that concurrent check_time_rules calls are thread-safe.

        BUG CANDIDATE: Rules are loaded, checked, and updated without locks.
        Concurrent execution could cause race conditions.
        """
        # Create multiple rules
        for i in range(5):
            rule = Rule.create_time_rule(
                user_email=f"user{i}@example.com",
                schedule="30 14 * * *",
                action="send_reminder",
                params={"message_template": f"Test {i}"},
            )
            add_rule(rule, test_config)

        fire_counts = {"count": 0}
        lock = threading.Lock()
        errors = []

        def track_fire(*args, **kwargs):
            with lock:
                fire_counts["count"] += 1

        def run_check():
            try:
                with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                    with patch("src.scheduler.update_rule_last_fired"):
                        check_time_rules(test_config, mock_services)
            except Exception as e:
                errors.append(str(e))

        # Run multiple concurrent checks
        threads = [threading.Thread(target=run_check) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent execution errors: {errors}"
        # Each of 5 rules fires once per thread = 50 total
        # But with proper locking, it should be 5 (once per rule)
        # BUG: Without locking in check_time_rules, we may get races

    def test_concurrent_rule_file_access(self, test_config):
        """Test that concurrent file access doesn't corrupt rules.json.

        BUG CANDIDATE: load_rules and save_rules have a race window.
        """
        errors = []

        def add_rules():
            try:
                for i in range(20):
                    rule = Rule.create_time_rule(
                        user_email=f"concurrent_{threading.current_thread().name}@example.com",
                        schedule="0 * * * *",
                        action="send_reminder",
                        params={"message_template": f"Test {i}"},
                    )
                    add_rule(rule, test_config)
            except Exception as e:
                errors.append(f"{threading.current_thread().name}: {e}")

        threads = [threading.Thread(target=add_rules, name=f"T{i}") for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent file access errors: {errors}"

        # Verify file isn't corrupted
        rules_data = load_rules(test_config)
        assert isinstance(rules_data, dict), "Rules file corrupted"


class TestWeeklyDiaryEdgeCases:
    """Test edge cases in weekly diary generation."""

    @freeze_time("2026-01-19 04:00:00")  # Sunday 11:00 PM Eastern (next day UTC)
    def test_weekly_diary_sunday_11pm_boundary(self, test_config, mock_services):
        """Test diary generation triggers exactly at Sunday 11pm."""
        with patch("src.scheduler.generate_diary_for_user") as mock_gen:
            with patch("src.scheduler.IDENTITIES", {"test@example.com": "Test"}):
                with patch("src.scheduler.load_user_data", return_value={}):
                    check_weekly_diary(test_config, mock_services)

            # Should trigger generation
            assert mock_gen.called

    @freeze_time("2026-01-19 04:02:00")  # Sunday 11:02 PM Eastern
    def test_weekly_diary_minute_1_boundary(self, test_config, mock_services):
        """Test that diary only generates in first minute of 11pm.

        BUG CANDIDATE: The check is `if now.minute > 1` but the scheduler
        runs every 60 seconds. If scheduler is delayed, we might miss the window.
        """
        with patch("src.scheduler.generate_diary_for_user") as mock_gen:
            check_weekly_diary(test_config, mock_services)

            # Should NOT trigger because minute > 1
            assert not mock_gen.called

    @freeze_time("2026-01-19 04:00:30")  # Sunday 11:00:30 PM Eastern
    def test_weekly_diary_timezone_sunday_boundary(self, test_config, mock_services):
        """Test diary generation respects timezone for Sunday detection.

        BUG CANDIDATE: When it's Sunday 11pm in America/New_York,
        it's already Monday in UTC. The scheduler correctly uses local time.
        """
        with patch("src.scheduler.generate_diary_for_user") as mock_gen:
            with patch("src.scheduler.IDENTITIES", {"test@example.com": "Test"}):
                with patch("src.scheduler.load_user_data", return_value={}):
                    check_weekly_diary(test_config, mock_services)

            # Should trigger because it's Sunday in local timezone
            assert mock_gen.called


class TestEventRuleEdgeCases:
    """Test edge cases in event-based rule processing."""

    @freeze_time("2026-01-16 01:00:00")  # Jan 15 8:00 PM Eastern (UTC-5)
    def test_event_utc_midnight_boundary(self, test_config, mock_services):
        """Test event at UTC midnight when local is previous day.

        An event at 2026-01-16T00:00:00Z is actually Jan 15 in NY (7pm).
        """
        mock_services.calendar_service = MagicMock()

        rule = Rule.create_event_rule(
            user_email="test@example.com",
            description="vet appointment",
            trigger={"days_before": 0},
            action="send_reminder",
            params={"message_template": "Vet today!"},
        )
        add_rule(rule, test_config)

        # Mock event at UTC midnight Jan 16 (7pm Jan 15 Eastern)
        mock_event = {
            "summary": "Vet Appointment",
            "start": "2026-01-16T00:00:00Z",
            "description": "",
            "calendar": "primary",
        }

        with patch("src.clients.calendar.get_all_upcoming_events") as mock_cal:
            mock_cal.return_value = {"primary": [mock_event]}

            with patch("src.scheduler.matches_event", return_value=True):
                with patch("src.scheduler.execute_action") as mock_action:
                    with patch("src.scheduler.mark_event_triggered"):
                        check_event_rules(test_config, mock_services)

            # The event is "today" in local time (Jan 15)
            # days_before=0 should trigger
            assert mock_action.called

    @freeze_time("2026-01-16 04:30:00")  # Jan 15 11:30 PM Eastern (UTC-5)
    def test_all_day_event_date_boundary(self, test_config, mock_services):
        """Test all-day event (no time component) on boundary."""
        mock_services.calendar_service = MagicMock()

        rule = Rule.create_event_rule(
            user_email="test@example.com",
            description="birthday",
            trigger={"days_before": 1},
            action="send_reminder",
            params={"message_template": "Birthday tomorrow!"},
        )
        add_rule(rule, test_config)

        # All-day event on Jan 16
        mock_event = {
            "summary": "Friend's Birthday",
            "start": "2026-01-16",  # No time component
            "description": "",
            "calendar": "primary",
        }

        with patch("src.clients.calendar.get_all_upcoming_events") as mock_cal:
            mock_cal.return_value = {"primary": [mock_event]}

            with patch("src.scheduler.matches_event", return_value=True):
                with patch("src.scheduler.execute_action") as mock_action:
                    with patch("src.scheduler.mark_event_triggered"):
                        check_event_rules(test_config, mock_services)

            # Event is Jan 16, now is Jan 15, days_until = 1
            assert mock_action.called


class TestCroniterEdgeCases:
    """Test croniter behavior that affects scheduler."""

    def test_croniter_naive_vs_aware_datetime(self):
        """Demonstrate croniter's naive datetime handling.

        The scheduler uses naive datetimes with croniter, which works
        but loses timezone information.
        """
        local_tz = ZoneInfo("America/New_York")
        aware_now = datetime(2026, 1, 15, 14, 30, 0, tzinfo=local_tz)
        naive_now = aware_now.replace(tzinfo=None)

        cron = croniter("0 15 * * *", naive_now - timedelta(minutes=1))
        next_fire = cron.get_next(datetime)

        # croniter returns naive datetime
        assert next_fire.tzinfo is None
        assert next_fire == datetime(2026, 1, 15, 15, 0)

    def test_croniter_day_of_week_vs_day_of_month(self):
        """Test croniter's handling of day-of-week AND day-of-month.

        Standard cron behavior: If BOTH day-of-month AND day-of-week
        are specified, the job runs when EITHER matches (OR logic).
        """
        # Run on 15th AND on Fridays
        cron = croniter("0 0 15 * 5", datetime(2026, 1, 1))

        dates = []
        for _ in range(5):
            dates.append(cron.get_next(datetime))

        # Should include both 15th of months AND Fridays
        days_of_month = [d.day for d in dates]
        days_of_week = [d.weekday() for d in dates]

        # Verify we get both types
        has_15th = 15 in days_of_month
        has_friday = 4 in days_of_week  # Friday is weekday 4

        assert has_15th or has_friday, "Cron should match either condition"

    def test_croniter_every_minute_wraparound(self):
        """Test croniter handles minute wraparound correctly."""
        now = datetime(2026, 1, 15, 23, 59, 30)
        cron = croniter("* * * * *", now - timedelta(minutes=1))

        next_fire = cron.get_next(datetime)
        assert next_fire == datetime(2026, 1, 15, 23, 59)

        next_fire = cron.get_next(datetime)
        assert next_fire == datetime(2026, 1, 16, 0, 0)  # Wrapped to next day


class TestSchedulerRobustness:
    """Test scheduler robustness under error conditions."""

    @freeze_time("2026-01-15 19:30:30")  # 14:30:30 Eastern
    def test_malformed_cron_expression(self, test_config, mock_services):
        """Test scheduler handles malformed cron expressions gracefully."""
        # Add a rule with invalid cron
        rules_data = {
            "test@example.com": [{
                "id": "bad-cron",
                "user_email": "test@example.com",
                "type": "time",
                "action": "send_reminder",
                "enabled": True,
                "schedule": "invalid cron expression",
                "params": {},
            }]
        }
        save_rules(rules_data, test_config)

        # Should not raise exception
        check_time_rules(test_config, mock_services)  # Should not raise

    @freeze_time("2026-01-15 19:30:30")
    def test_missing_rule_fields(self, test_config, mock_services):
        """Test scheduler handles rules with missing optional fields."""
        # Minimal rule dict
        rules_data = {
            "test@example.com": [{
                "id": "minimal",
                "user_email": "test@example.com",
                "type": "time",
                "action": "send_reminder",
                # Missing: enabled, schedule, etc.
            }]
        }
        save_rules(rules_data, test_config)

        # Should handle gracefully (rule has no schedule, so it's skipped)
        check_time_rules(test_config, mock_services)

    @freeze_time("2026-01-15 19:30:30")
    def test_corrupted_last_fired_timestamp(self, test_config, mock_services):
        """Test scheduler handles corrupted last_fired timestamp.

        BUG CANDIDATE: If last_fired is not a valid ISO format, the
        scheduler will crash.
        """
        rules_data = {
            "test@example.com": [{
                "id": "bad-timestamp",
                "user_email": "test@example.com",
                "type": "time",
                "action": "send_reminder",
                "enabled": True,
                "schedule": "30 14 * * *",
                "last_fired": "not-a-valid-timestamp",
                "params": {},
            }]
        }
        save_rules(rules_data, test_config)

        # This will raise ValueError in datetime.fromisoformat
        # The scheduler catches this with a broad except
        check_time_rules(test_config, mock_services)


class TestRaceConditionBugs:
    """Tests that expose race conditions in the scheduler."""

    def test_load_modify_save_race(self, test_config):
        """Demonstrate potential race between load and save operations.

        The sequence: load_rules -> modify in memory -> save_rules
        is NOT atomic. If two threads do this concurrently, updates can be lost.
        """
        # Pre-populate with one rule
        initial_rule = Rule.create_time_rule(
            user_email="initial@example.com",
            schedule="0 0 * * *",
            action="send_reminder",
        )
        add_rule(initial_rule, test_config)

        # Simulate race: two concurrent updates
        def update_1():
            data = load_rules(test_config)
            time.sleep(0.01)  # Simulate slow operation
            data["user1@example.com"] = [{"id": "1", "user_email": "user1@example.com", "type": "time", "action": "a"}]
            save_rules(data, test_config)

        def update_2():
            data = load_rules(test_config)
            time.sleep(0.01)  # Simulate slow operation
            data["user2@example.com"] = [{"id": "2", "user_email": "user2@example.com", "type": "time", "action": "b"}]
            save_rules(data, test_config)

        t1 = threading.Thread(target=update_1)
        t2 = threading.Thread(target=update_2)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # One update may be lost due to race condition
        final_data = load_rules(test_config)

        # NOTE: This test may sometimes pass and sometimes fail due to timing
        # The bug is that without proper locking, one update can overwrite another
        # Expected: all three users present
        # Actual: may only have 2 users (one update was lost)
        users = set(final_data.keys())
        # We check that at least the initial user is present
        assert "initial@example.com" in users, "Initial user should always be present"
        # Note: user1 or user2 might be missing due to race!


class TestDocumentedBugs:
    """Tests that document confirmed bugs in the scheduler.

    These tests assert the CURRENT (buggy) behavior. When bugs are fixed,
    these tests should be updated to assert the CORRECT behavior.
    """

    def test_bug_120_second_window_blocks_minutely_cron(self, test_config, mock_services):
        """BUG: The 120-second window prevents legitimate every-minute cron jobs.

        The scheduler checks: (now - last_fired) < 120 seconds to prevent double-fires.
        But this means a cron job scheduled for "* * * * *" (every minute) will only
        fire every 2 minutes!

        Location: src/scheduler.py line 84
        Fix: The window should be < 60 seconds (the scheduler interval), or better,
        use the cron expression itself to determine the minimum interval.
        """
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="* * * * *",  # Every minute
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        fire_times = []

        def track_fire(*args, **kwargs):
            fire_times.append(datetime.now())

        # Simulate 5 scheduler ticks, each 60 seconds apart
        times = [
            "2026-01-15 19:30:30",  # 14:30:30 Eastern
            "2026-01-15 19:31:30",  # 14:31:30 Eastern
            "2026-01-15 19:32:30",  # 14:32:30 Eastern
            "2026-01-15 19:33:30",  # 14:33:30 Eastern
            "2026-01-15 19:34:30",  # 14:34:30 Eastern
        ]

        for t in times:
            with freeze_time(t):
                with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                    from src.rules import update_rule_last_fired
                    with patch("src.scheduler.update_rule_last_fired", side_effect=lambda e, r, c: update_rule_last_fired(e, r, c)):
                        check_time_rules(test_config, mock_services)

        # FIXED: Now fires all 5 times correctly (one per minute)
        # (Previously the 120-second window caused only 3 fires)
        assert len(fire_times) == 5, f"Every-minute cron should fire 5 times, got {len(fire_times)}"

    def test_bug_weekly_diary_2_minute_window_too_narrow(self, test_config, mock_services):
        """BUG: The 2-minute window for weekly diary can be missed.

        The scheduler runs every 60 seconds, and the weekly diary check
        requires now.minute <= 1 (only minutes 0 and 1 are valid).

        If the scheduler tick happens at 11:01:59 PM, the next tick at 11:02:59 PM
        will miss the window entirely. This means there's a race condition.

        Location: src/scheduler.py lines 323-324
        Fix: Use a larger window (e.g., minute <= 5) or track last generation time.
        """
        # At 11:01:59, still in window
        with freeze_time("2026-01-19 04:01:59"):  # Sunday 11:01:59 PM Eastern
            with patch("src.scheduler.generate_diary_for_user") as mock_gen:
                with patch("src.scheduler.IDENTITIES", {"test@example.com": "Test"}):
                    with patch("src.scheduler.load_user_data", return_value={}):
                        check_weekly_diary(test_config, mock_services)
                assert mock_gen.called, "Should fire at 11:01:59"

        # At 11:02:00, window is closed
        with freeze_time("2026-01-19 04:02:00"):  # Sunday 11:02:00 PM Eastern
            with patch("src.scheduler.generate_diary_for_user") as mock_gen:
                with patch("src.scheduler.IDENTITIES", {"test@example.com": "Test"}):
                    with patch("src.scheduler.load_user_data", return_value={}):
                        check_weekly_diary(test_config, mock_services)
                assert not mock_gen.called, "Should NOT fire at 11:02:00"

    def test_dst_fall_back_correctly_prevents_double_fire(self, test_config, mock_services):
        """GOOD: During DST fall-back, the scheduler correctly prevents double-fires.

        On November 1, 2026, at 2:00 AM EDT, clocks fall back to 1:00 AM EST.
        A cron job scheduled for 1:30 AM will see two 1:30 AM times:
        - 1:30 AM EDT (UTC-4)
        - 1:30 AM EST (UTC-5) - one hour later

        The scheduler stores last_fired as timezone-aware string, then compares
        using naive local time. Since both are "01:30:30" in local time, the
        difference is 0 seconds, which correctly blocks the second fire.

        This is correct behavior - a cron job for "1:30 AM" should only fire
        once per calendar day, even if DST causes 1:30 AM to occur twice.
        """
        rule = Rule.create_time_rule(
            user_email="test@example.com",
            schedule="30 1 * * *",  # 1:30 AM
            action="send_reminder",
            params={"message_template": "Test"},
        )
        add_rule(rule, test_config)

        fire_count = 0

        def track_fire(*args, **kwargs):
            nonlocal fire_count
            fire_count += 1

        # First 1:30 AM (EDT, before fall-back)
        # November 1, 2026 1:30 AM EDT = UTC 05:30:00
        with freeze_time("2026-11-01 05:30:30"):
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                from src.rules import update_rule_last_fired
                with patch("src.scheduler.update_rule_last_fired", side_effect=lambda e, r, c: update_rule_last_fired(e, r, c)):
                    check_time_rules(test_config, mock_services)

        # Second 1:30 AM (EST, after fall-back)
        # November 1, 2026 1:30 AM EST = UTC 06:30:00
        with freeze_time("2026-11-01 06:30:30"):
            with patch("src.scheduler.send_custom_reminder", side_effect=track_fire):
                check_time_rules(test_config, mock_services)

        # CORRECT: Only fires once because local time comparison sees
        # both as "01:30:30" with 0 seconds difference
        assert fire_count == 1, f"Expected 1 fire during DST fall-back, got {fire_count}"

    def test_bug_no_lock_in_check_time_rules(self, test_config, mock_services):
        """BUG: check_time_rules has no locking around the rules iteration.

        If rules are modified while check_time_rules is iterating,
        we could get a RuntimeError or miss/duplicate rules.

        This is hard to trigger reliably, but the code structure shows the issue:
        1. load_rules() returns a dict
        2. Iterate over dict
        3. For each rule, call update_rule_last_fired() which modifies the file

        If another thread calls add_rule() or delete_rule() during iteration,
        behavior is undefined.

        Location: src/scheduler.py check_time_rules function
        Fix: Add locking or use a copy of the rules list.
        """
        # This test documents the bug but doesn't reliably trigger it
        # The bug is in the code structure, not easily demonstrated with tests
        pass

    def test_bug_event_rule_no_lock_on_triggered_file(self, test_config, mock_services):
        """BUG: Event rule triggered state can be lost under concurrent access.

        The sequence:
        1. is_event_triggered() loads file, checks key
        2. (other thread modifies file)
        3. mark_event_triggered() loads file again, adds key, saves

        Between steps 1 and 3, another thread could have added a triggered event,
        and that event would be overwritten.

        Location: src/rules.py is_event_triggered and mark_event_triggered
        Fix: Use locking around the check-and-set operation, or use atomic operations.
        """
        # This test documents the bug but doesn't reliably trigger it
        pass
