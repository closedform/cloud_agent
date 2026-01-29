"""Calendar tool functions for CalendarAgent."""

from datetime import datetime
from typing import Any

from src.clients import calendar as calendar_client
from src.config import Config, get_config
from src.services import Services


def _validate_datetime_format(time_str: str, field_name: str) -> str | None:
    """Validate datetime string format.

    Args:
        time_str: The datetime string to validate.
        field_name: Name of the field for error messages.

    Returns:
        Error message if invalid, None if valid.
    """
    if not time_str or not time_str.strip():
        return f"{field_name} cannot be empty"

    # Strip whitespace
    time_str = time_str.strip()

    # Try to parse as ISO format (with or without timezone)
    # Accept: YYYY-MM-DDTHH:MM:SS, YYYY-MM-DDTHH:MM:SS+HH:MM, YYYY-MM-DDTHH:MM:SSZ
    try:
        # Remove timezone suffix for parsing
        parse_str = time_str
        if parse_str.endswith("Z"):
            parse_str = parse_str[:-1]
        elif "+" in parse_str[10:]:  # After date portion
            parse_str = parse_str.split("+")[0]
        elif parse_str.count("-") > 2:  # Has negative offset like -05:00
            # Find the timezone offset (last - after position 10)
            last_minus = parse_str.rfind("-")
            if last_minus > 10:
                parse_str = parse_str[:last_minus]

        datetime.fromisoformat(parse_str)
    except ValueError:
        return f"{field_name} must be in ISO format (YYYY-MM-DDTHH:MM:SS)"

    return None


def _validate_time_order(start_time: str, end_time: str) -> str | None:
    """Validate that end time is after start time.

    Args:
        start_time: Start time in ISO format.
        end_time: End time in ISO format.

    Returns:
        Error message if invalid, None if valid.
    """
    try:
        # Parse, stripping timezone suffixes
        def parse_iso(s: str) -> datetime:
            s = s.strip()
            if s.endswith("Z"):
                s = s[:-1]
            elif "+" in s[10:]:
                s = s.split("+")[0]
            elif s.count("-") > 2:
                last_minus = s.rfind("-")
                if last_minus > 10:
                    s = s[:last_minus]
            return datetime.fromisoformat(s)

        start_dt = parse_iso(start_time)
        end_dt = parse_iso(end_time)

        if end_dt <= start_dt:
            return "End time must be after start time"
    except ValueError:
        # Validation already done by _validate_datetime_format
        pass

    return None


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
        summary: Event title/summary (required, max 1024 characters).
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS).
        end_time: End time in ISO format (YYYY-MM-DDTHH:MM:SS). Must be after start_time.
        calendar_name: Name of calendar to add event to (default: primary).
        description: Optional event description (max 8192 characters).
        recurrence: Optional RRULE string for recurring events (e.g., "RRULE:FREQ=WEEKLY;BYDAY=MO").

    Returns:
        Dictionary with status and event details or error message.
    """
    # Validate summary
    if not summary or not summary.strip():
        return {"status": "error", "message": "Event summary cannot be empty"}
    summary = summary.strip()
    if len(summary) > 1024:
        return {
            "status": "error",
            "message": f"Event summary too long ({len(summary)} chars, max 1024)",
        }

    # Validate description length
    if description and len(description) > 8192:
        return {
            "status": "error",
            "message": f"Description too long ({len(description)} chars, max 8192)",
        }

    # Validate datetime formats
    start_error = _validate_datetime_format(start_time, "start_time")
    if start_error:
        return {"status": "error", "message": start_error}

    end_error = _validate_datetime_format(end_time, "end_time")
    if end_error:
        return {"status": "error", "message": end_error}

    # Validate time order
    order_error = _validate_time_order(start_time, end_time)
    if order_error:
        return {"status": "error", "message": order_error}

    config, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    target_cal_id, cal_name_resolved = _resolve_calendar_id(
        calendar_name, services.calendars
    )

    try:
        event_result = calendar_client.add_event(
            services.calendar_service,
            summary=summary,
            start_time_iso=start_time.strip(),
            end_time_iso=end_time.strip(),
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
                "start": start_time.strip(),
                "end": end_time.strip(),
                "calendar": cal_name_resolved,
                "link": event_result.get("htmlLink") if event_result else None,
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create event: {e}"}


def query_calendar_events(
    calendar_name: str | None = None,
    max_results: int = 10,
    time_min: str | None = None,
    time_max: str | None = None,
) -> dict[str, Any]:
    """Query calendar events.

    Args:
        calendar_name: Optional specific calendar to query. If None, queries all.
        max_results: Maximum number of events to return per calendar (default: 10).
        time_min: Optional start of time range in ISO format (YYYY-MM-DDTHH:MM:SS).
            Defaults to now (upcoming events only).
        time_max: Optional end of time range in ISO format (YYYY-MM-DDTHH:MM:SS).
            If not specified, no upper bound.

    Returns:
        Dictionary with events organized by calendar.
    """
    from zoneinfo import ZoneInfo

    config, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    # Validate time_min if provided
    if time_min:
        error = _validate_datetime_format(time_min, "time_min")
        if error:
            return {"status": "error", "message": error}

    # Validate time_max if provided
    if time_max:
        error = _validate_datetime_format(time_max, "time_max")
        if error:
            return {"status": "error", "message": error}

    # Validate time range order if both provided
    if time_min and time_max:
        order_error = _validate_time_order(time_min, time_max)
        if order_error:
            return {"status": "error", "message": order_error}

    try:
        # Determine if we need date-range query or standard upcoming query
        use_range_query = time_min is not None or time_max is not None

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

            if use_range_query:
                # Parse datetime strings and add timezone
                tz = ZoneInfo(config.timezone)

                def parse_iso_with_tz(s: str, fallback_tz: ZoneInfo) -> datetime:
                    """Parse ISO datetime, handling various timezone formats."""
                    s = s.strip()
                    if s.endswith("Z"):
                        s = s[:-1] + "+00:00"
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=fallback_tz)
                    return dt

                dt_min = (
                    parse_iso_with_tz(time_min, tz)
                    if time_min
                    else datetime.now(tz)
                )
                dt_max = (
                    parse_iso_with_tz(time_max, tz)
                    if time_max
                    else None
                )

                if dt_max:
                    events = calendar_client.get_events_in_range(
                        services.calendar_service, cal_id, dt_min, dt_max, max_results
                    )
                else:
                    events = calendar_client.get_upcoming_events(
                        services.calendar_service, cal_id, max_results
                    )
            else:
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
            if use_range_query:
                tz = ZoneInfo(config.timezone)

                def parse_iso_with_tz(s: str, fallback_tz: ZoneInfo) -> datetime:
                    """Parse ISO datetime, handling various timezone formats."""
                    s = s.strip()
                    if s.endswith("Z"):
                        s = s[:-1] + "+00:00"
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=fallback_tz)
                    return dt

                dt_min = (
                    parse_iso_with_tz(time_min, tz)
                    if time_min
                    else datetime.now(tz)
                )
                dt_max = (
                    parse_iso_with_tz(time_max, tz)
                    if time_max
                    else None
                )

                if dt_max:
                    all_events = calendar_client.get_all_events_in_range(
                        services.calendar_service, dt_min, dt_max, max_results
                    )
                else:
                    all_events = calendar_client.get_all_upcoming_events(
                        services.calendar_service, max_results_per_calendar=max_results
                    )
            else:
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
    _, services = _get_config_and_services()
    if not services or not services.calendar_service:
        return {"status": "error", "message": "Calendar service not available"}

    return {
        "status": "success",
        "calendars": list(services.calendars.keys()),
        "calendar_map": services.calendars,
    }

