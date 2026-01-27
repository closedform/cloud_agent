"""Calendar tool functions for CalendarAgent."""

from typing import Any

from src.clients import calendar as calendar_client
from src.config import Config, get_config
from src.services import Services


def _get_config_and_services() -> tuple[Config, Services | None]:
    """Get config and services from global state."""
    from src.agents.tools._context import get_services

    return get_config(), get_services()


def _resolve_calendar_id(
    calendar_name: str, calendars: dict[str, str]
) -> tuple[str, str]:
    """Resolve calendar name to ID with fuzzy matching.

    Args:
        calendar_name: User-provided calendar name.
        calendars: Available calendars map (name -> id).

    Returns:
        Tuple of (calendar_id, resolved_name).
    """
    name_lower = calendar_name.lower()

    # Exact match
    if name_lower in calendars:
        return calendars[name_lower], name_lower

    # Fuzzy match (substring in either direction)
    for key in calendars:
        if name_lower in key or key in name_lower:
            return calendars[key], key

    # Fall back to primary
    return calendars.get("primary", "primary"), "primary"


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_name: str = "primary",
    description: str = "",
    recurrence: str | None = None,
) -> dict[str, Any]:
    """Create a new calendar event.

    Args:
        summary: Event title/summary.
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS).
        end_time: End time in ISO format (YYYY-MM-DDTHH:MM:SS).
        calendar_name: Name of calendar to add event to (default: primary).
        description: Optional event description.
        recurrence: Optional RRULE string for recurring events.

    Returns:
        Dictionary with status and event details or error message.
    """
    config, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    target_cal_id, cal_name_resolved = _resolve_calendar_id(
        calendar_name, services.calendars
    )

    try:
        calendar_client.add_event(
            services.calendar_service,
            summary=summary,
            start_time_iso=start_time,
            end_time_iso=end_time,
            description=description,
            calendar_id=target_cal_id,
            recurrence=recurrence,
            timezone=config.timezone,
        )
        return {
            "status": "success",
            "message": f"Created event '{summary}' on {cal_name_resolved}",
            "event": {
                "summary": summary,
                "start": start_time,
                "end": end_time,
                "calendar": cal_name_resolved,
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create event: {e}"}


def query_calendar_events(
    calendar_name: str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """Query upcoming calendar events.

    Args:
        calendar_name: Optional specific calendar to query. If None, queries all.
        max_results: Maximum number of events to return per calendar.

    Returns:
        Dictionary with events organized by calendar.
    """
    config, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    try:
        if calendar_name:
            # Query specific calendar
            cal_id, cal_name_resolved = _resolve_calendar_id(
                calendar_name, services.calendars
            )
            # If resolved to "primary" but wasn't requested, calendar not found
            if cal_name_resolved == "primary" and calendar_name.lower() != "primary":
                return {
                    "status": "error",
                    "message": f"Calendar '{calendar_name}' not found",
                    "available_calendars": list(services.calendars.keys()),
                }

            events = calendar_client.get_upcoming_events(
                services.calendar_service, cal_id, max_results
            )
            return {
                "status": "success",
                "calendars": {cal_name_resolved: events},
                "total_events": len(events),
            }
        else:
            # Query all calendars
            all_events = calendar_client.get_all_upcoming_events(
                services.calendar_service, max_results_per_calendar=max_results
            )
            total = sum(len(events) for events in all_events.values())
            return {
                "status": "success",
                "calendars": all_events,
                "total_events": total,
            }

    except Exception as e:
        return {"status": "error", "message": f"Failed to query events: {e}"}


def list_calendars() -> dict[str, Any]:
    """List all available calendars.

    Returns:
        Dictionary with calendar names and IDs.
    """
    config, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    return {
        "status": "success",
        "calendars": list(services.calendars.keys()),
        "calendar_map": services.calendars,
    }

