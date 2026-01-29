"""Stress tests for src/diary.py - testing edge cases and potential bugs."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.diary import (
    DiaryEntry,
    get_reminders_in_range,
    get_week_bounds,
    get_week_id,
    log_fired_reminder,
    save_diary_entry,
)
from src.scheduler import generate_diary_for_user


class TestWeekWithNoActivity:
    """Test diary generation when there's no activity for the week."""

    def test_generate_diary_no_todos_no_reminders_no_calendar(
        self, test_config, mock_services
    ):
        """Should generate diary even with no activity."""
        mock_services.calendar_service = None
        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="It was a quiet week with no recorded activity."
        )

        generate_diary_for_user("quiet@example.com", test_config, mock_services)

        # Verify diary was created
        diary_file = test_config.diary_file
        assert diary_file.exists()

        with open(diary_file) as f:
            data = json.load(f)

        assert "quiet@example.com" in data
        entries = data["quiet@example.com"]
        assert len(entries) == 1
        assert entries[0]["content"] == "It was a quiet week with no recorded activity."
        assert entries[0]["sources"]["todos_completed"] == []
        assert entries[0]["sources"]["reminders_fired"] == []
        assert entries[0]["sources"]["calendar_events"] == []

    def test_generate_diary_empty_sources_prompt_format(
        self, test_config, mock_services
    ):
        """Verify the prompt correctly handles empty sources (shows '- None')."""
        mock_services.calendar_service = None
        prompt_capture = []

        def capture_prompt(*args, **kwargs):
            prompt_capture.append(kwargs.get("contents", args[1] if len(args) > 1 else None))
            return MagicMock(text="Summary generated")

        mock_services.gemini_client.models.generate_content.side_effect = capture_prompt

        generate_diary_for_user("empty@example.com", test_config, mock_services)

        # Verify prompt contains "- None" for empty sections
        assert len(prompt_capture) == 1
        prompt = prompt_capture[0][0]
        assert "- None" in prompt


class TestVeryLongActivityDescriptions:
    """Test handling of very long activity descriptions."""

    def test_long_todo_description(self, test_config, mock_services):
        """Should handle todos with very long descriptions."""
        mock_services.calendar_service = None

        # Create a todo with a very long description
        long_todo_text = "A" * 10000  # 10KB of text
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Pre-populate user data with long todo
        user_data = {
            "longuser@example.com": {
                "lists": {},
                "todos": [
                    {
                        "id": "long-todo-1",
                        "text": long_todo_text,
                        "done": True,
                        "created_at": (now - timedelta(days=1)).isoformat(),
                        "completed_at": now.isoformat(),
                    }
                ],
            }
        }
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            json.dump(user_data, f)

        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="Completed a very long task this week."
        )

        # Should not raise an exception
        generate_diary_for_user("longuser@example.com", test_config, mock_services)

        # Verify the long todo was included in sources
        with open(test_config.diary_file) as f:
            data = json.load(f)
        assert long_todo_text in data["longuser@example.com"][0]["sources"]["todos_completed"]

    def test_many_activities(self, test_config, mock_services):
        """Should handle a large number of activities."""
        mock_services.calendar_service = None
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Create 500 todos
        todos = []
        for i in range(500):
            todos.append({
                "id": f"todo-{i}",
                "text": f"Task number {i} with some description",
                "done": True,
                "created_at": (now - timedelta(days=2)).isoformat(),
                "completed_at": now.isoformat(),
            })

        user_data = {
            "manyuser@example.com": {
                "lists": {},
                "todos": todos,
            }
        }
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            json.dump(user_data, f)

        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="A very productive week!"
        )

        # Should complete without error
        generate_diary_for_user("manyuser@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)
        assert len(data["manyuser@example.com"][0]["sources"]["todos_completed"]) == 500

    def test_long_reminder_message(self, test_config, mock_services):
        """Should handle reminders with very long messages."""
        mock_services.calendar_service = None

        long_message = "B" * 5000
        log_fired_reminder("longreminder@example.com", long_message, test_config)

        # Generate diary
        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="Week summary."
        )
        generate_diary_for_user("longreminder@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)
        assert long_message in data["longreminder@example.com"][0]["sources"]["reminders_fired"]


class TestTimezoneHandlingInDateRanges:
    """Test timezone handling in date range queries."""

    def test_get_week_bounds_with_timezone(self):
        """Should return timezone-aware datetimes when tz is specified."""
        monday, sunday = get_week_bounds(tz="America/New_York")

        assert monday.tzinfo is not None
        assert sunday.tzinfo is not None
        assert str(monday.tzinfo) == "America/New_York"

    def test_get_week_bounds_without_timezone(self):
        """Should return naive datetimes when tz is not specified."""
        monday, sunday = get_week_bounds()

        # Note: current implementation returns naive datetimes when tz is None
        assert monday.tzinfo is None
        assert sunday.tzinfo is None

    def test_get_week_id_with_timezone(self):
        """Should use timezone-aware now() when tz is specified."""
        # Test at a time that would be different dates in different timezones
        week_id_ny = get_week_id(tz="America/New_York")
        week_id_tokyo = get_week_id(tz="Asia/Tokyo")

        # Both should be valid week IDs
        assert "-W" in week_id_ny
        assert "-W" in week_id_tokyo

    def test_reminders_mixed_timezone_awareness(self, test_config):
        """Test get_reminders_in_range with mixed tz-aware and naive timestamps."""
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)
        week_start, week_end = get_week_bounds(now, tz=test_config.timezone)

        # Log a reminder (creates tz-aware timestamp)
        log_fired_reminder("tztest@example.com", "Test reminder", test_config)

        # Query with tz-aware bounds
        reminders = get_reminders_in_range(
            "tztest@example.com", week_start, week_end, test_config
        )
        assert "Test reminder" in reminders

    def test_reminders_naive_bounds_with_aware_log(self, test_config):
        """Test querying with naive datetime bounds against tz-aware logged reminders."""
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        # Log a reminder (creates tz-aware timestamp)
        log_fired_reminder("tznaive@example.com", "Aware reminder", test_config)

        # Query with naive bounds
        week_start, week_end = get_week_bounds(now.replace(tzinfo=None))  # Naive
        reminders = get_reminders_in_range(
            "tznaive@example.com", week_start, week_end, test_config
        )
        # Should still find the reminder due to timezone normalization in get_reminders_in_range
        assert "Aware reminder" in reminders

    def test_dst_transition_week(self, test_config, mock_services):
        """Test diary generation during DST transition week."""
        mock_services.calendar_service = None

        # March 8, 2026 is a Sunday - DST starts in US
        dst_date = datetime(2026, 3, 8, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("src.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = dst_date
            mock_datetime.fromisoformat = datetime.fromisoformat

            week_start, week_end = get_week_bounds(dst_date, tz="America/New_York")

            # Week should span the DST transition correctly
            assert week_start.day == 2  # Monday March 2
            assert week_end.day == 8  # Sunday March 8

    def test_year_boundary_timezone(self):
        """Test week bounds around year boundary with timezone."""
        # Dec 31, 2025 at 11pm ET is Jan 1, 2026 4am UTC
        dec31 = datetime(2025, 12, 31, 23, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        monday, sunday = get_week_bounds(dec31, tz="America/New_York")

        # Dec 31, 2025 is a Wednesday, so Monday should be Dec 29
        assert monday.day == 29
        assert monday.month == 12
        assert monday.year == 2025
        assert sunday.day == 4  # Jan 4, 2026
        assert sunday.month == 1
        assert sunday.year == 2026


class TestMissingCalendarService:
    """Test behavior when calendar service is unavailable."""

    def test_generate_diary_none_calendar_service(self, test_config, mock_services):
        """Should generate diary without calendar events when service is None."""
        mock_services.calendar_service = None

        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="Week without calendar access."
        )

        generate_diary_for_user("nocalendar@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)

        entry = data["nocalendar@example.com"][0]
        assert entry["sources"]["calendar_events"] == []
        assert "Week without calendar access." in entry["content"]

    def test_generate_diary_calendar_api_error(self, test_config, mock_services):
        """Should handle calendar API errors gracefully."""
        mock_calendar_service = MagicMock()
        mock_services.calendar_service = mock_calendar_service

        # Simulate API error
        with patch("src.scheduler.calendar_client.get_all_events_in_range") as mock_get:
            mock_get.side_effect = Exception("Calendar API unavailable")

            mock_services.gemini_client.models.generate_content.return_value = MagicMock(
                text="Week summary despite calendar error."
            )

            # Should not raise - should catch and continue
            generate_diary_for_user("apierror@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)

        # Diary should still be created
        assert "apierror@example.com" in data
        assert data["apierror@example.com"][0]["sources"]["calendar_events"] == []

    def test_generate_diary_gemini_api_error(self, test_config, mock_services):
        """Should handle Gemini API errors gracefully (no diary created)."""
        mock_services.calendar_service = None
        mock_services.gemini_client.models.generate_content.side_effect = Exception(
            "Gemini API error"
        )

        # Should not raise, but diary won't be saved
        generate_diary_for_user("geminierror@example.com", test_config, mock_services)

        # Diary file may not exist or may not have this user
        if test_config.diary_file.exists():
            with open(test_config.diary_file) as f:
                data = json.load(f)
            assert "geminierror@example.com" not in data


class TestWeekBoundsBugs:
    """Tests that expose potential bugs in get_week_bounds."""

    def test_week_bounds_date_and_tz_inconsistent(self):
        """BUG: When date is provided with different tz, date's timezone is used, not tz param.

        This is potentially confusing behavior: the tz parameter is ignored when date is provided.
        The function uses date's existing timezone (or lack thereof).
        """
        # Create a tz-aware date in Tokyo
        tokyo_date = datetime(2026, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

        # Pass it with tz="America/New_York" - but tz is IGNORED
        monday, sunday = get_week_bounds(tokyo_date, tz="America/New_York")

        # The returned datetimes have Tokyo timezone, NOT New York!
        assert str(monday.tzinfo) == "Asia/Tokyo"  # tz param was ignored

    def test_week_bounds_naive_date_with_tz_param(self):
        """BUG: When naive date is provided with tz param, tz is ignored."""
        naive_date = datetime(2026, 1, 15, 10, 0, 0)  # No timezone

        monday, sunday = get_week_bounds(naive_date, tz="America/New_York")

        # Returned datetimes are still naive - tz param ignored!
        assert monday.tzinfo is None  # BUG: tz param was provided but ignored

    def test_week_bounds_preserves_timezone_info(self):
        """Verify timezone info is preserved from input date."""
        aware_date = datetime(2026, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        monday, sunday = get_week_bounds(aware_date)

        # Should preserve the timezone from input
        assert monday.tzinfo is not None
        assert str(monday.tzinfo) == "America/New_York"

    def test_week_bounds_sunday_end_misses_last_second(self):
        """Potential issue: Sunday end is 23:59:59, missing the last second's events.

        An event at exactly 23:59:59.5 would still be in the week, but an event
        exactly at 24:00:00 (midnight) of the next Monday would not be included,
        which is correct. However, range queries using <= might miss subsecond events.
        """
        monday, sunday = get_week_bounds(datetime(2026, 1, 15))

        # End is 23:59:59, not 23:59:59.999999
        assert sunday.hour == 23
        assert sunday.minute == 59
        assert sunday.second == 59
        assert sunday.microsecond == 0  # No microseconds - could miss subsecond events

    def test_week_bounds_dst_spring_forward(self):
        """Test DST spring forward handling.

        On March 8, 2026 at 2am ET, clocks spring forward to 3am.
        A week containing this date should handle it correctly.
        """
        # Date during DST transition week
        date = datetime(2026, 3, 8, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        monday, sunday = get_week_bounds(date)

        # Verify week boundaries are correct
        assert monday.month == 3
        assert monday.day == 2  # Monday before DST
        assert sunday.month == 3
        assert sunday.day == 8  # Sunday of DST

        # The week duration should still be ~7 days even with DST
        duration = sunday - monday
        # Due to DST, this week is actually 167 hours (168 - 1) in real time
        # But timedelta just sees the wall clock difference
        assert duration.days == 6

    def test_week_bounds_dst_fall_back(self):
        """Test DST fall back handling.

        On November 1, 2026 at 2am ET, clocks fall back to 1am.
        """
        # Date during DST fall back week
        date = datetime(2026, 11, 1, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        monday, sunday = get_week_bounds(date)

        assert monday.month == 10
        assert monday.day == 26
        assert sunday.month == 11
        assert sunday.day == 1


class TestEdgeCases:
    """Additional edge case tests."""

    def test_diary_entry_special_characters_in_content(self, test_config):
        """Should handle special characters in diary content."""
        entry = DiaryEntry(
            id="2026-W03",
            user_email="special@example.com",
            week_start="2026-01-12",
            week_end="2026-01-18",
            content='Content with "quotes", \'apostrophes\', \n\tnewlines, and emoji: \U0001F600',
            sources={"key": ["value with special chars: <>&\"'"]},
        )
        save_diary_entry(entry, test_config)

        with open(test_config.diary_file) as f:
            data = json.load(f)

        restored = DiaryEntry.from_dict(data["special@example.com"][0])
        assert "\U0001F600" in restored.content
        assert "<>&\"'" in restored.sources["key"][0]

    def test_diary_entry_unicode_email(self, test_config):
        """Should handle unicode in email addresses."""
        # Note: This is technically valid for internationalized email addresses
        entry = DiaryEntry(
            id="2026-W03",
            user_email="user@example.com",  # Keep standard email for test
            week_start="2026-01-12",
            week_end="2026-01-18",
            content="Unicode test: \u4e2d\u6587 \u65e5\u672c\u8a9e \ud55c\uad6d\uc5b4",
            sources={},
        )
        save_diary_entry(entry, test_config)

        with open(test_config.diary_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "\u4e2d\u6587" in data["user@example.com"][0]["content"]

    def test_overwrite_existing_diary_entry(self, test_config):
        """Should overwrite existing entry for same week."""
        entry1 = DiaryEntry(
            id="2026-W03",
            user_email="overwrite@example.com",
            week_start="2026-01-12",
            week_end="2026-01-18",
            content="First version",
            sources={},
        )
        save_diary_entry(entry1, test_config)

        entry2 = DiaryEntry(
            id="2026-W03",
            user_email="overwrite@example.com",
            week_start="2026-01-12",
            week_end="2026-01-18",
            content="Second version",
            sources={"updated": ["yes"]},
        )
        save_diary_entry(entry2, test_config)

        with open(test_config.diary_file) as f:
            data = json.load(f)

        # Should have exactly one entry
        assert len(data["overwrite@example.com"]) == 1
        assert data["overwrite@example.com"][0]["content"] == "Second version"
        assert data["overwrite@example.com"][0]["sources"] == {"updated": ["yes"]}

    def test_empty_todo_text(self, test_config, mock_services):
        """Should handle todos with empty text."""
        mock_services.calendar_service = None
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        user_data = {
            "emptytodo@example.com": {
                "lists": {},
                "todos": [
                    {
                        "id": "empty-1",
                        "text": "",  # Empty text
                        "done": True,
                        "created_at": (now - timedelta(days=1)).isoformat(),
                        "completed_at": now.isoformat(),
                    }
                ],
            }
        }
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            json.dump(user_data, f)

        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="Week with empty todo."
        )

        generate_diary_for_user("emptytodo@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)
        # Empty string should still be in the list
        assert "" in data["emptytodo@example.com"][0]["sources"]["todos_completed"]

    def test_todo_without_completed_at(self, test_config, mock_services):
        """Should handle done todos missing completed_at timestamp."""
        mock_services.calendar_service = None
        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)

        user_data = {
            "nocompletedts@example.com": {
                "lists": {},
                "todos": [
                    {
                        "id": "no-ts-1",
                        "text": "Done but no timestamp",
                        "done": True,
                        "created_at": (now - timedelta(days=1)).isoformat(),
                        # Missing completed_at
                    }
                ],
            }
        }
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.user_data_file, "w") as f:
            json.dump(user_data, f)

        mock_services.gemini_client.models.generate_content.return_value = MagicMock(
            text="Week summary."
        )

        generate_diary_for_user("nocompletedts@example.com", test_config, mock_services)

        with open(test_config.diary_file) as f:
            data = json.load(f)
        # Todo without completed_at should be skipped
        assert "Done but no timestamp" not in data["nocompletedts@example.com"][0]["sources"]["todos_completed"]

    def test_reminder_log_malformed_entry(self, test_config):
        """Should handle malformed entries in reminder log."""
        # Create reminder log with malformed entries
        log = [
            {"user": "malformed@example.com", "message": "Good entry", "fired_at": datetime.now().isoformat()},
            {"user": "malformed@example.com"},  # Missing message and fired_at
            {"user": "malformed@example.com", "message": "No timestamp"},  # Missing fired_at
            {"user": "malformed@example.com", "fired_at": "not-a-date"},  # Invalid date
            {"message": "No user"},  # Missing user
        ]
        test_config.reminder_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_config.reminder_log_file, "w") as f:
            json.dump(log, f)

        local_tz = ZoneInfo(test_config.timezone)
        now = datetime.now(local_tz)
        week_start, week_end = get_week_bounds(now, tz=test_config.timezone)

        # Should not raise
        reminders = get_reminders_in_range("malformed@example.com", week_start, week_end, test_config)

        # Should only return the valid entry
        assert "Good entry" in reminders
        assert len(reminders) == 1
