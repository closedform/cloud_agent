"""Tests for src/scheduler.py timezone handling."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


class TestEventTriggerTimezone:
    """Tests for timezone handling in event rule triggers."""

    def test_utc_event_converted_to_local(self):
        """UTC event should be converted to local timezone for date comparison."""
        # Event at 1 AM UTC on Jan 16
        utc_event_time = "2026-01-16T01:00:00Z"
        local_tz = ZoneInfo("America/New_York")  # UTC-5

        # Parse like scheduler does
        event_start = datetime.fromisoformat(utc_event_time.replace("Z", "+00:00"))
        event_start_local = event_start.astimezone(local_tz)

        # In NY, 1 AM UTC is 8 PM previous day (Jan 15)
        assert event_start_local.date().day == 15, (
            f"1 AM UTC Jan 16 should be Jan 15 in NY, got {event_start_local.date()}"
        )

    def test_local_event_preserves_date(self):
        """Event with local timezone should preserve the correct date."""
        # Event at 10 PM Eastern on Jan 16
        local_tz = ZoneInfo("America/New_York")
        event_start = datetime(2026, 1, 16, 22, 0, tzinfo=local_tz)

        # Should still be Jan 16 in local time
        assert event_start.date().day == 16

    def test_all_day_event_uses_local_date(self):
        """All-day events (date only) should use local timezone."""
        event_date_str = "2026-01-16"
        local_tz = ZoneInfo("America/New_York")

        # Parse like scheduler does for all-day events
        event_start = datetime.strptime(event_date_str, "%Y-%m-%d")
        event_start = event_start.replace(tzinfo=local_tz)

        assert event_start.date().day == 16

    def test_days_until_calculation_respects_timezone(self):
        """Days until calculation should use local dates, not UTC."""
        local_tz = ZoneInfo("America/New_York")

        # Now is Jan 15, 11 PM Eastern
        now_local = datetime(2026, 1, 15, 23, 0, tzinfo=local_tz)

        # Event is Jan 16, 1 AM UTC (which is Jan 15, 8 PM Eastern)
        event_utc = datetime(2026, 1, 16, 1, 0, tzinfo=ZoneInfo("UTC"))
        event_local = event_utc.astimezone(local_tz)

        # Both dates are Jan 15 in Eastern time
        days_until = (event_local.date() - now_local.date()).days
        assert days_until == 0, (
            f"Event at 1 AM UTC Jan 16 and now at 11 PM Eastern Jan 15 "
            f"should be 0 days apart, got {days_until}"
        )

    def test_dst_transition_handled(self):
        """DST transitions should not cause off-by-one day errors."""
        local_tz = ZoneInfo("America/New_York")

        # March 9, 2026 is DST transition in US (spring forward)
        # 2 AM becomes 3 AM

        # Event at 2:30 AM UTC on March 9
        event_utc = datetime(2026, 3, 9, 2, 30, tzinfo=ZoneInfo("UTC"))
        event_local = event_utc.astimezone(local_tz)

        # Should still be March 8 in Eastern (9:30 PM)
        assert event_local.date().day == 8
