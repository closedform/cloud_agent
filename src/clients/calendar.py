"""Google Calendar client library.

Provides functions for calendar operations. CLI functionality has been
moved to src/cli/calendar_cli.py.
"""

import datetime
import sys
from typing import TYPE_CHECKING, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

if TYPE_CHECKING:
    from src.config import Config

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_service(config: "Config") -> Any:
    """Authenticate with Google and return the Calendar service.

    Args:
        config: Application configuration containing token/credentials paths.

    Returns:
        Google Calendar service object.
    """
    creds = None
    token_path = config.token_path
    creds_path = config.credentials_path

    # The file token.json stores the user's access and refresh tokens
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print(f"Error: credentials.json not found at {creds_path}.")
                print(
                    "Please follow the README instructions to download your "
                    "credentials from Google Cloud Console."
                )
                sys.exit(1)

            print("Launching browser for authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def add_event(
    service: Any,
    summary: str,
    start_time_iso: str,
    end_time_iso: str,
    description: str = "",
    calendar_id: str = "primary",
    recurrence: str | None = None,
    timezone: str = "America/New_York",
) -> None:
    """Add an event to the specified calendar.

    Args:
        service: Google Calendar service object.
        summary: Event title.
        start_time_iso: Start time in ISO format (YYYY-MM-DDTHH:MM:SS).
        end_time_iso: End time in ISO format.
        description: Event description.
        calendar_id: Calendar ID (default: primary).
        recurrence: RRULE string for recurring events.
        timezone: Timezone for the event.
    """
    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_time_iso,
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_time_iso,
            "timeZone": timezone,
        },
    }

    if recurrence:
        event["recurrence"] = [recurrence]

    try:
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"SUCCESS: Created event '{summary}' on calendar '{calendar_id}'")
        print(f"Link: {event_result.get('htmlLink')}")
    except HttpError as error:
        print(f"FAILED to create event '{summary}': {error}")


def get_calendar_map(service: Any) -> dict[str, str]:
    """Get a mapping of calendar names to their IDs.

    Args:
        service: Google Calendar service object.

    Returns:
        Dictionary mapping lowercase calendar names to calendar IDs.
    """
    calendar_map = {}
    try:
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for entry in calendar_list["items"]:
                key = entry["summary"].lower()
                calendar_map[key] = entry["id"]
            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break
    except HttpError as error:
        print(f"Error fetching calendars: {error}")
    return calendar_map


def list_calendars(service: Any) -> None:
    """Print all calendars on the user's account.

    Args:
        service: Google Calendar service object.
    """
    cal_map = get_calendar_map(service)
    for name, cal_id in cal_map.items():
        print(f"Calendar: {name} (ID: {cal_id})")


def create_calendar(service: Any, summary: str, timezone: str = "America/New_York") -> str | None:
    """Create a new secondary calendar.

    Args:
        service: Google Calendar service object.
        summary: Name for the new calendar.
        timezone: Timezone for the calendar.

    Returns:
        The new calendar's ID, or None on failure.
    """
    calendar = {
        "summary": summary,
        "timeZone": timezone,
    }
    try:
        created_calendar = service.calendars().insert(body=calendar).execute()
        print(f"SUCCESS: Created new calendar '{summary}' (ID: {created_calendar['id']})")
        return created_calendar["id"]
    except HttpError as error:
        print(f"FAILED to create calendar '{summary}': {error}")
        return None


def list_events(service: Any, calendar_id: str = "primary", max_results: int = 10) -> None:
    """Print the next few upcoming events on the specified calendar.

    Args:
        service: Google Calendar service object.
        calendar_id: Calendar ID to list events from.
        max_results: Maximum number of events to show.
    """
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        print(f"Getting the next {max_results} upcoming events for calendar: {calendar_id}")
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            print("No upcoming events found.")
            return

        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            print(f"{start} - {event['summary']}")
    except HttpError as error:
        print(f"An error occurred: {error}")


def get_upcoming_events(
    service: Any,
    calendar_id: str = "primary",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Get upcoming events as a list of dictionaries.

    Args:
        service: Google Calendar service object.
        calendar_id: Calendar ID to get events from.
        max_results: Maximum number of events to return.

    Returns:
        List of event dictionaries with summary, start, end, description.
    """
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        result = []
        for event in events:
            result.append(
                {
                    "summary": event.get("summary", "No title"),
                    "start": event["start"].get("dateTime", event["start"].get("date")),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                    "description": event.get("description", ""),
                }
            )
        return result
    except HttpError as error:
        print(f"Error fetching events: {error}")
        return []


def get_all_upcoming_events(
    service: Any,
    max_results_per_calendar: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Get events from all calendars.

    Args:
        service: Google Calendar service object.
        max_results_per_calendar: Maximum events per calendar.

    Returns:
        Dictionary mapping calendar names to lists of events.
    """
    all_events = {}
    cal_map = get_calendar_map(service)

    for cal_name, cal_id in cal_map.items():
        events = get_upcoming_events(service, cal_id, max_results_per_calendar)
        if events:
            all_events[cal_name] = events

    return all_events
