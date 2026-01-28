"""Tests for src/agents/tools/calendar_tools.py"""

from unittest.mock import MagicMock, patch

import pytest


class TestCalendarToolsServiceUnavailable:
    """Tests for error handling when services are unavailable."""

    def test_create_event_no_services(self):
        """create_calendar_event returns error when services is None."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = None

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Test Event",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
            )

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]

    def test_create_event_no_calendar_service(self):
        """create_calendar_event returns error when calendar_service is None."""
        mock_services = MagicMock()
        mock_services.calendar_service = None
        mock_services.calendars = {"primary": "primary"}

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = mock_services

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Test Event",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
            )

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]

    def test_query_events_no_services(self):
        """query_calendar_events returns error when services is None."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = None

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events()

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]

    def test_query_events_no_calendar_service(self):
        """query_calendar_events returns error when calendar_service is None."""
        mock_services = MagicMock()
        mock_services.calendar_service = None
        mock_services.calendars = {"primary": "primary"}

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = mock_services

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events()

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]

    def test_list_calendars_no_services(self):
        """list_calendars returns error when services is None."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = None

            from src.agents.tools.calendar_tools import list_calendars

            result = list_calendars()

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]

    def test_list_calendars_no_calendar_service(self):
        """list_calendars returns error when calendar_service is None."""
        mock_services = MagicMock()
        mock_services.calendar_service = None
        mock_services.calendars = {"primary": "primary"}

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services:
            mock_get_services.return_value = mock_services

            from src.agents.tools.calendar_tools import list_calendars

            result = list_calendars()

            assert result["status"] == "error"
            assert "Calendar service not available" in result["message"]


class TestCreateCalendarEvent:
    """Tests for create_calendar_event tool function."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {
            "primary": "primary",
            "work": "work-calendar-id",
            "personal": "personal-calendar-id",
        }
        return mock_services

    def test_create_event_success_primary(self, mock_calendar_services, test_config):
        """Successfully create event on primary calendar."""
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
                summary="Team Meeting",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
            )

            assert result["status"] == "success"
            assert "Team Meeting" in result["message"]
            assert result["event"]["summary"] == "Team Meeting"
            assert result["event"]["start"] == "2026-01-27T10:00:00"
            assert result["event"]["end"] == "2026-01-27T11:00:00"
            assert result["event"]["calendar"] == "primary"

            mock_add_event.assert_called_once_with(
                mock_calendar_services.calendar_service,
                summary="Team Meeting",
                start_time_iso="2026-01-27T10:00:00",
                end_time_iso="2026-01-27T11:00:00",
                description="",
                calendar_id="primary",
                recurrence=None,
                timezone=test_config.timezone,
            )

    def test_create_event_success_named_calendar(
        self, mock_calendar_services, test_config
    ):
        """Successfully create event on a named calendar."""
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
                summary="Doctor Appointment",
                start_time="2026-01-28T14:00:00",
                end_time="2026-01-28T15:00:00",
                calendar_name="personal",
                description="Annual checkup",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "personal"

            mock_add_event.assert_called_once_with(
                mock_calendar_services.calendar_service,
                summary="Doctor Appointment",
                start_time_iso="2026-01-28T14:00:00",
                end_time_iso="2026-01-28T15:00:00",
                description="Annual checkup",
                calendar_id="personal-calendar-id",
                recurrence=None,
                timezone=test_config.timezone,
            )

    def test_create_event_with_recurrence(self, mock_calendar_services, test_config):
        """Successfully create recurring event."""
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
                summary="Weekly Standup",
                start_time="2026-01-27T09:00:00",
                end_time="2026-01-27T09:30:00",
                calendar_name="work",
                recurrence="RRULE:FREQ=WEEKLY;BYDAY=MO",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "work"

            mock_add_event.assert_called_once()
            call_kwargs = mock_add_event.call_args.kwargs
            assert call_kwargs["recurrence"] == "RRULE:FREQ=WEEKLY;BYDAY=MO"

    def test_create_event_api_error(self, mock_calendar_services, test_config):
        """Handle API error when creating event."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.add_event"
        ) as mock_add_event:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_add_event.side_effect = Exception("API rate limit exceeded")

            from src.agents.tools.calendar_tools import create_calendar_event

            result = create_calendar_event(
                summary="Test Event",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
            )

            assert result["status"] == "error"
            assert "Failed to create event" in result["message"]
            assert "API rate limit exceeded" in result["message"]


class TestCalendarNameResolution:
    """Tests for calendar name resolution (exact match, fuzzy match, fallback)."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with multiple calendars."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {
            "primary": "primary",
            "work calendar": "work-calendar-id",
            "personal": "personal-calendar-id",
            "family events": "family-events-id",
        }
        return mock_services

    def test_exact_match_calendar_name(self, mock_calendar_services, test_config):
        """Exact match calendar name resolution."""
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
                summary="Test",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
                calendar_name="personal",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "personal"
            mock_add_event.assert_called_once()
            assert mock_add_event.call_args.kwargs["calendar_id"] == "personal-calendar-id"

    def test_case_insensitive_match(self, mock_calendar_services, test_config):
        """Calendar name matching is case-insensitive."""
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
                summary="Test",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
                calendar_name="PERSONAL",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "personal"

    def test_fuzzy_match_partial_name(self, mock_calendar_services, test_config):
        """Fuzzy match when search term is contained in calendar name."""
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

            # "work" should match "work calendar"
            result = create_calendar_event(
                summary="Test",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
                calendar_name="work",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "work calendar"

    def test_fuzzy_match_calendar_name_contained_in_search(
        self, mock_calendar_services, test_config
    ):
        """Fuzzy match when calendar name is contained in search term."""
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

            # "my personal calendar" contains "personal"
            result = create_calendar_event(
                summary="Test",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
                calendar_name="my personal calendar",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "personal"

    def test_fallback_to_primary(self, mock_calendar_services, test_config):
        """Fallback to primary calendar when no match found."""
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
                summary="Test",
                start_time="2026-01-27T10:00:00",
                end_time="2026-01-27T11:00:00",
                calendar_name="nonexistent",
            )

            assert result["status"] == "success"
            assert result["event"]["calendar"] == "primary"
            mock_add_event.assert_called_once()
            assert mock_add_event.call_args.kwargs["calendar_id"] == "primary"


class TestQueryCalendarEvents:
    """Tests for query_calendar_events tool function."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {
            "primary": "primary",
            "work": "work-calendar-id",
            "personal": "personal-calendar-id",
        }
        return mock_services

    def test_query_all_calendars(self, mock_calendar_services, test_config):
        """Query all calendars when no calendar_name specified."""
        mock_events = {
            "primary": [
                {"summary": "Event 1", "start": "2026-01-27T10:00:00"},
            ],
            "work": [
                {"summary": "Meeting", "start": "2026-01-27T14:00:00"},
            ],
        }

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.get_all_upcoming_events"
        ) as mock_get_all:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_get_all.return_value = mock_events

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events()

            assert result["status"] == "success"
            assert result["total_events"] == 2
            assert "primary" in result["calendars"]
            assert "work" in result["calendars"]
            mock_get_all.assert_called_once_with(
                mock_calendar_services.calendar_service, max_results_per_calendar=10
            )

    def test_query_specific_calendar(self, mock_calendar_services, test_config):
        """Query a specific calendar by name."""
        mock_events = [
            {"summary": "Work Meeting", "start": "2026-01-27T09:00:00"},
            {"summary": "Standup", "start": "2026-01-27T10:00:00"},
        ]

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.get_upcoming_events"
        ) as mock_get_events:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_get_events.return_value = mock_events

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events(calendar_name="work", max_results=5)

            assert result["status"] == "success"
            assert result["total_events"] == 2
            assert "work" in result["calendars"]
            assert result["calendars"]["work"] == mock_events
            mock_get_events.assert_called_once_with(
                mock_calendar_services.calendar_service, "work-calendar-id", 5
            )

    def test_query_specific_calendar_fuzzy_match(
        self, mock_calendar_services, test_config
    ):
        """Query a specific calendar using fuzzy name matching."""
        mock_events = [{"summary": "Personal Event", "start": "2026-01-27T12:00:00"}]

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.get_upcoming_events"
        ) as mock_get_events:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_get_events.return_value = mock_events

            from src.agents.tools.calendar_tools import query_calendar_events

            # Use partial name that should fuzzy match "personal"
            result = query_calendar_events(calendar_name="person")

            assert result["status"] == "success"
            assert "personal" in result["calendars"]

    def test_query_calendar_not_found(self, mock_calendar_services, test_config):
        """Query returns error when calendar not found."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events(calendar_name="nonexistent")

            assert result["status"] == "error"
            assert "not found" in result["message"]
            assert "available_calendars" in result
            assert "primary" in result["available_calendars"]

    def test_query_api_error(self, mock_calendar_services, test_config):
        """Handle API error when querying events."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.get_all_upcoming_events"
        ) as mock_get_all:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_get_all.side_effect = Exception("Network error")

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events()

            assert result["status"] == "error"
            assert "Failed to query events" in result["message"]
            assert "Network error" in result["message"]

    def test_query_empty_results(self, mock_calendar_services, test_config):
        """Query returns success with empty results."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config, patch(
            "src.agents.tools.calendar_tools.calendar_client.get_all_upcoming_events"
        ) as mock_get_all:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config
            mock_get_all.return_value = {}

            from src.agents.tools.calendar_tools import query_calendar_events

            result = query_calendar_events()

            assert result["status"] == "success"
            assert result["total_events"] == 0
            assert result["calendars"] == {}


class TestListCalendars:
    """Tests for list_calendars tool function."""

    @pytest.fixture
    def mock_calendar_services(self):
        """Create mock services with calendar service."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {
            "primary": "primary",
            "work": "work-calendar-id",
            "personal": "personal-calendar-id",
        }
        return mock_services

    def test_list_calendars_success(self, mock_calendar_services, test_config):
        """Successfully list all calendars."""
        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_calendar_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import list_calendars

            result = list_calendars()

            assert result["status"] == "success"
            assert "calendars" in result
            assert "calendar_map" in result
            assert set(result["calendars"]) == {"primary", "work", "personal"}
            assert result["calendar_map"]["work"] == "work-calendar-id"

    def test_list_calendars_only_primary(self, test_config):
        """List calendars when only primary exists."""
        mock_services = MagicMock()
        mock_services.calendar_service = MagicMock()
        mock_services.calendars = {"primary": "primary"}

        with patch(
            "src.agents.tools._context.get_services"
        ) as mock_get_services, patch(
            "src.agents.tools.calendar_tools.get_config"
        ) as mock_get_config:
            mock_get_services.return_value = mock_services
            mock_get_config.return_value = test_config

            from src.agents.tools.calendar_tools import list_calendars

            result = list_calendars()

            assert result["status"] == "success"
            assert result["calendars"] == ["primary"]
            assert result["calendar_map"] == {"primary": "primary"}
