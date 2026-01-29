"""Stress tests for calendar tools - hunting for edge case bugs.

Tests cover:
1. Events spanning multiple days
2. Timezone conversions
3. Invalid date/time formats
4. Very long event descriptions
"""

from unittest.mock import MagicMock, patch, call

import pytest


class TestMultiDayEvents:
    """Tests for events that span multiple days."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {
            "primary": "primary",
            "work": "work-calendar-id",
        }
        return mock_services

    def test_create_multi_day_event(self, mock_calendar_services, test_config):
        """Create an event spanning multiple days."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # 3-day conference
            result = create_calendar_event(
                summary="Tech Conference",
                start_time="2026-02-01T09:00:00",
                end_time="2026-02-03T18:00:00",
                description="Annual tech conference spanning 3 days",
            )

            assert result["status"] == "success"
            assert result["event"]["start"] == "2026-02-01T09:00:00"
            assert result["event"]["end"] == "2026-02-03T18:00:00"
            mock_add_event.assert_called_once()

    def test_create_week_long_event(self, mock_calendar_services, test_config):
        """Create an event spanning an entire week."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # Week-long vacation
            result = create_calendar_event(
                summary="Vacation",
                start_time="2026-03-01T00:00:00",
                end_time="2026-03-07T23:59:59",
            )

            assert result["status"] == "success"

    def test_create_event_crossing_month_boundary(self, mock_calendar_services, test_config):
        """Create an event crossing a month boundary."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Month-crossing Event",
                start_time="2026-01-30T10:00:00",
                end_time="2026-02-02T10:00:00",
            )

            assert result["status"] == "success"

    def test_create_event_crossing_year_boundary(self, mock_calendar_services, test_config):
        """Create an event crossing a year boundary."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="New Year Party",
                start_time="2026-12-31T20:00:00",
                end_time="2027-01-01T03:00:00",
            )

            assert result["status"] == "success"

    def test_create_event_end_before_start_bug(self, mock_calendar_services, test_config):
        """BUG HUNT: Event where end time is before start time should fail.

        The calendar_tools module does NOT validate that end_time > start_time.
        This is passed directly to the Google Calendar API which may reject it
        or behave unexpectedly.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            # Simulate API rejecting invalid time range
            mock_add_event.side_effect = Exception("Invalid time range: end before start")

            from src.agents.tools.calendar_tools import create_calendar_event

            # End time before start time - this is invalid!
            result = create_calendar_event(
                summary="Invalid Event",
                start_time="2026-01-28T15:00:00",
                end_time="2026-01-28T10:00:00",  # End is before start!
            )

            # Without API validation, this would pass through to Google
            # Currently relies on Google API to catch this
            assert result["status"] == "error"


class TestTimezoneConversions:
    """Tests for timezone handling."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {"primary": "primary"}
        return mock_services

    def test_event_with_default_timezone(self, mock_calendar_services, test_config):
        """Event creation uses config timezone."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Meeting",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
            )

            assert result["status"] == "success"
            # Verify timezone from config is passed to API
            call_kwargs = mock_add_event.call_args.kwargs
            assert call_kwargs["timezone"] == "America/New_York"

    def test_event_with_utc_offset_in_time_string(self, mock_calendar_services, test_config):
        """BUG HUNT: ISO string with UTC offset - does the API handle it?

        The tool accepts ISO format strings. If user provides timezone offset
        in the string (e.g., 2026-01-28T10:00:00+05:00), this might conflict
        with the timezone parameter sent to Google Calendar API.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # Time string includes UTC offset
            result = create_calendar_event(
                summary="Meeting",
                start_time="2026-01-28T10:00:00+05:00",  # Has offset!
                end_time="2026-01-28T11:00:00+05:00",
            )

            # The tool doesn't validate/strip timezone from the string
            # It sends both the string AND a timezone parameter to Google
            # This could cause confusion about which timezone is actually used
            assert result["status"] == "success"
            call_kwargs = mock_add_event.call_args.kwargs
            # Time string has +05:00 but timezone param says America/New_York
            # Potential conflict!
            assert call_kwargs["start_time_iso"] == "2026-01-28T10:00:00+05:00"
            assert call_kwargs["timezone"] == "America/New_York"

    def test_event_with_z_utc_suffix(self, mock_calendar_services, test_config):
        """Test ISO string with Z suffix for UTC."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # UTC time with Z suffix
            result = create_calendar_event(
                summary="UTC Meeting",
                start_time="2026-01-28T15:00:00Z",
                end_time="2026-01-28T16:00:00Z",
            )

            assert result["status"] == "success"

    def test_dst_transition_spring_forward(self, mock_calendar_services, test_config):
        """BUG HUNT: Event during DST spring-forward transition.

        In America/New_York, 2:00 AM on second Sunday of March doesn't exist
        (clocks jump from 1:59 AM to 3:00 AM).
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # March 8, 2026 is a Sunday - DST spring forward
            # 2:30 AM doesn't exist in America/New_York
            result = create_calendar_event(
                summary="Impossible Time Meeting",
                start_time="2026-03-08T02:30:00",  # This time doesn't exist!
                end_time="2026-03-08T03:30:00",
            )

            # The tool doesn't validate DST transitions
            # Google Calendar API may interpret this in unpredictable ways
            assert result["status"] == "success"

    def test_dst_transition_fall_back(self, mock_calendar_services, test_config):
        """BUG HUNT: Event during DST fall-back transition.

        In America/New_York, 1:00-2:00 AM on first Sunday of November exists twice.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # November 1, 2026 is a Sunday - DST fall back
            # 1:30 AM exists twice!
            result = create_calendar_event(
                summary="Ambiguous Time Meeting",
                start_time="2026-11-01T01:30:00",  # This time exists twice!
                end_time="2026-11-01T02:30:00",
            )

            # No disambiguation - which 1:30 AM is this?
            assert result["status"] == "success"


class TestInvalidDateTimeFormats:
    """Tests for invalid date/time format handling."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {"primary": "primary"}
        return mock_services

    def test_invalid_iso_format_missing_time(self, mock_calendar_services, test_config):
        """BUG HUNT: Date-only string without time component.

        The docstring says YYYY-MM-DDTHH:MM:SS but doesn't validate this.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            # Simulate API error for invalid format
            mock_add_event.side_effect = Exception("Invalid dateTime format")

            from src.agents.tools.calendar_tools import create_calendar_event

            # Date only - no time component
            result = create_calendar_event(
                summary="All Day Event",
                start_time="2026-01-28",  # Missing time!
                end_time="2026-01-29",
            )

            # No validation at tool level - passed directly to API
            assert result["status"] == "error"

    def test_completely_invalid_date_string(self, mock_calendar_services, test_config):
        """BUG HUNT: Completely invalid date string."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid date format")

            from src.agents.tools.calendar_tools import create_calendar_event

            # Completely garbage input
            result = create_calendar_event(
                summary="Invalid Event",
                start_time="not-a-date",
                end_time="also-not-a-date",
            )

            # Passed through without validation, API catches it
            assert result["status"] == "error"

    def test_impossible_date_feb_30(self, mock_calendar_services, test_config):
        """BUG HUNT: February 30th doesn't exist."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid date")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Impossible Event",
                start_time="2026-02-30T10:00:00",  # Feb 30 doesn't exist!
                end_time="2026-02-30T11:00:00",
            )

            assert result["status"] == "error"

    def test_impossible_date_feb_29_non_leap_year(self, mock_calendar_services, test_config):
        """BUG HUNT: February 29th in non-leap year."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid date")

            from src.agents.tools.calendar_tools import create_calendar_event

            # 2027 is not a leap year
            result = create_calendar_event(
                summary="Non-Leap Year Event",
                start_time="2027-02-29T10:00:00",  # 2027 is not a leap year!
                end_time="2027-02-29T11:00:00",
            )

            assert result["status"] == "error"

    def test_invalid_time_24_hours(self, mock_calendar_services, test_config):
        """Hour 24 is technically valid in ISO 8601 but Python's fromisoformat rejects it."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # Hour 24:00:00 means midnight at end of day
            result = create_calendar_event(
                summary="Midnight Event",
                start_time="2026-01-28T23:00:00",
                end_time="2026-01-28T24:00:00",  # Hour 24?
            )

            # Now validated - hour 24 is rejected by Python's datetime.fromisoformat
            assert result["status"] == "error"
            assert "ISO format" in result["message"]

    def test_invalid_time_60_minutes(self, mock_calendar_services, test_config):
        """BUG HUNT: 60 minutes is invalid."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid time")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Invalid Minutes",
                start_time="2026-01-28T10:60:00",  # 60 minutes is invalid!
                end_time="2026-01-28T11:00:00",
            )

            assert result["status"] == "error"

    def test_empty_strings(self, mock_calendar_services, test_config):
        """BUG HUNT: Empty string inputs."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Empty dateTime")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Empty Dates",
                start_time="",
                end_time="",
            )

            assert result["status"] == "error"

    def test_whitespace_only_times(self, mock_calendar_services, test_config):
        """BUG HUNT: Whitespace-only time strings."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid dateTime")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Whitespace Dates",
                start_time="   ",
                end_time="   ",
            )

            assert result["status"] == "error"


class TestVeryLongDescriptions:
    """Tests for very long event descriptions."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {"primary": "primary"}
        return mock_services

    def test_normal_description(self, mock_calendar_services, test_config):
        """Normal description length works fine."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Normal Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description="This is a normal description.",
            )

            assert result["status"] == "success"

    def test_1kb_description(self, mock_calendar_services, test_config):
        """1 KB description should work."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "A" * 1024  # 1 KB

            result = create_calendar_event(
                summary="1KB Description Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            assert result["status"] == "success"

    def test_10kb_description(self, mock_calendar_services, test_config):
        """10 KB description exceeds the 8192 character limit."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "B" * 10240  # 10 KB

            result = create_calendar_event(
                summary="10KB Description Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            # Now validated - description exceeds 8192 limit
            assert result["status"] == "error"
            assert "too long" in result["message"]

    def test_100kb_description_potential_limit(self, mock_calendar_services, test_config):
        """BUG HUNT: 100 KB description may hit API limits.

        Google Calendar API has a limit on event description size.
        The tool doesn't validate or truncate.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Description too long")

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "C" * 102400  # 100 KB

            result = create_calendar_event(
                summary="100KB Description Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            # No pre-validation, API rejects it
            assert result["status"] == "error"

    def test_1mb_description_bug(self, mock_calendar_services, test_config):
        """BUG HUNT: 1 MB description will definitely hit limits.

        This could cause memory issues or very slow API calls.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Request entity too large")

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "D" * 1048576  # 1 MB

            result = create_calendar_event(
                summary="1MB Description Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            # No pre-validation, sent to API which rejects
            assert result["status"] == "error"

    def test_description_with_unicode(self, mock_calendar_services, test_config):
        """Description with various unicode characters."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "Meeting with \u4e2d\u6587 and \u65e5\u672c\u8a9e and \ud83c\udf89 emoji and \u0627\u0644\u0639\u0631\u0628\u064a\u0629"

            result = create_calendar_event(
                summary="Unicode Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            assert result["status"] == "success"

    def test_description_with_html(self, mock_calendar_services, test_config):
        """Description containing HTML tags."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "<b>Bold</b> <script>alert('xss')</script> <a href='http://evil.com'>Link</a>"

            result = create_calendar_event(
                summary="HTML Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            # No sanitization at tool level
            assert result["status"] == "success"

    def test_description_with_newlines(self, mock_calendar_services, test_config):
        """Description with many newlines."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            description = "Line 1\n" * 1000  # 1000 lines

            result = create_calendar_event(
                summary="Multi-line Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                description=description,
            )

            assert result["status"] == "success"

    def test_very_long_summary(self, mock_calendar_services, test_config):
        """BUG HUNT: Very long event summary/title.

        Summaries also have length limits.
        """
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Summary too long")

            from src.agents.tools.calendar_tools import create_calendar_event

            summary = "E" * 10000  # Very long title

            result = create_calendar_event(
                summary=summary,
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
            )

            # No validation at tool level
            assert result["status"] == "error"

    def test_empty_summary(self, mock_calendar_services, test_config):
        """Empty event summary is now properly rejected."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="",  # Empty title!
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
            )

            # Now validated - empty summary is rejected
            assert result["status"] == "error"
            assert "cannot be empty" in result["message"]


class TestCalendarClientAddEvent:
    """Direct tests of the calendar client add_event function."""

    def test_add_event_exception_raised_on_http_error(self):
        """FIXED: add_event now re-raises HttpError after printing.

        The calendar_client.add_event function used to catch HttpError and print
        but not raise. This was fixed so that create_calendar_event properly
        catches the exception and returns an error status.
        """
        mock_service = MagicMock()
        from googleapiclient.errors import HttpError

        # Simulate API error
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.reason = "Bad Request"
        http_error = HttpError(mock_response, b'{"error": "invalid"}')

        mock_service.events().insert().execute.side_effect = http_error

        from src.clients.calendar import add_event
        import pytest

        # Now properly raises the exception
        with pytest.raises(HttpError):
            add_event(
                mock_service,
                summary="Test",
                start_time_iso="2026-01-28T10:00:00",
                end_time_iso="2026-01-28T11:00:00",
            )


class TestRecurrenceRules:
    """Tests for recurring event edge cases."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {"primary": "primary"}
        return mock_services

    def test_invalid_rrule_syntax(self, mock_calendar_services, test_config):
        """BUG HUNT: Invalid RRULE syntax."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("Invalid RRULE")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Bad Recurrence",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T11:00:00",
                recurrence="NOT_A_VALID_RRULE",
            )

            # No RRULE validation at tool level
            assert result["status"] == "error"

    def test_very_high_frequency_rrule(self, mock_calendar_services, test_config):
        """BUG HUNT: RRULE with very high frequency could create many events."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import create_calendar_event

            # Hourly recurrence forever - could create thousands of events
            result = create_calendar_event(
                summary="Hourly Event",
                start_time="2026-01-28T10:00:00",
                end_time="2026-01-28T10:30:00",
                recurrence="RRULE:FREQ=HOURLY",
            )

            # No guard against resource-intensive recurrence rules
            assert result["status"] == "success"
