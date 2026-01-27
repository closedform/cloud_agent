"""CLI for Google Calendar operations.

Run with: python -m src.cli.calendar_cli --help
"""

import argparse
import sys

from src.clients import calendar as calendar_client
from src.config import get_config


def main() -> None:
    """CLI entry point for calendar operations."""
    parser = argparse.ArgumentParser(description="Google Calendar Agent Tool")
    parser.add_argument("--summary", help="Event title")
    parser.add_argument("--start", help="Start time (ISO 8601: YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--end", help="End time (ISO 8601: YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--description", help="Event description", default="")
    parser.add_argument(
        "--calendar-id",
        help="ID of the calendar to add event to (default: primary)",
        default="primary",
    )
    parser.add_argument(
        "--recurrence",
        help="RRULE string (e.g., 'RRULE:FREQ=WEEKLY;BYDAY=MO')",
    )
    parser.add_argument(
        "--list-calendars",
        action="store_true",
        help="List all available calendars",
    )
    parser.add_argument(
        "--list-events",
        action="store_true",
        help="List upcoming events for the calendar",
    )
    parser.add_argument(
        "--create-calendar",
        help="Name of new calendar to create",
    )

    args = parser.parse_args()

    # Load config and authenticate
    config = get_config()
    service = calendar_client.get_service(config)

    # Handle CLI commands
    if args.create_calendar:
        calendar_client.create_calendar(service, args.create_calendar)
        return

    if args.list_calendars:
        calendar_client.list_calendars(service)
        return

    if args.list_events:
        calendar_client.list_events(service, args.calendar_id)
        return

    if args.summary and args.start and args.end:
        print(f"Adding event: {args.summary}...")
        calendar_client.add_event(
            service,
            args.summary,
            args.start,
            args.end,
            args.description,
            args.calendar_id,
            args.recurrence,
        )
        return

    # Default: show usage
    print("--- Google Calendar Tool ---")
    print("Authentication successful.\n")
    print("Usage: python -m src.cli.calendar_cli --help")


if __name__ == "__main__":
    main()
