import datetime
import os.path
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Set your timezone here
TIMEZONE = 'America/New_York'

def get_service():
    """
    Authenticates with Google and returns the Calendar service.
    """
    creds = None
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(script_dir, "token.json")
    creds_path = os.path.join(script_dir, "credentials.json")
    
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                print(f"Error: credentials.json not found at {creds_path}.")
                print("Please follow the README instructions to download your credentials from Google Cloud Console.")
                sys.exit(1)
            
            print("Launching browser for authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                creds_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service

def add_event(service, summary, start_time_iso, end_time_iso, description="", calendar_id='primary', recurrence=None):
    """
    Adds an event to the specified calendar (default: primary).
    start_time_iso and end_time_iso should be strings in ISO format, e.g. '2025-01-26T09:00:00'.
    recurrence should be a list of RRULE strings, e.g. ["RRULE:FREQ=WEEKLY;BYDAY=MO"]
    """
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time_iso,
            'timeZone': TIMEZONE,
        },
        'end': {
            'dateTime': end_time_iso,
            'timeZone': TIMEZONE,
        },
    }
    
    if recurrence:
        event['recurrence'] = [recurrence]

    try:
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"SUCCESS: Created event '{summary}' on calendar '{calendar_id}'")
        print(f"Link: {event_result.get('htmlLink')}")
    except HttpError as error:
        print(f"FAILED to create event '{summary}': {error}")

def get_calendar_map(service):
    """
    Returns a dictionary mapping lowercase calendar summaries to their IDs.
    Example: {'brandon': 'c_123...', 'primary': 'primary'}
    """
    calendar_map = {}
    try:
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for entry in calendar_list['items']:
                # Normalize keys to lowercase for easier matching
                key = entry['summary'].lower()
                calendar_map[key] = entry['id']
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break
    except HttpError as error:
        print(f"Error fetching calendars: {error}")
    return calendar_map

def list_calendars(service):
    """
    Lists all calendars on the user's account.
    """
    cal_map = get_calendar_map(service)
    for name, cal_id in cal_map.items():
        print(f"Calendar: {name} (ID: {cal_id})")

def create_calendar(service, summary):
    """
    Creates a new secondary calendar.
    """
    calendar = {
        'summary': summary,
        'timeZone': TIMEZONE
    }
    try:
        created_calendar = service.calendars().insert(body=calendar).execute()
        print(f"SUCCESS: Created new calendar '{summary}' (ID: {created_calendar['id']})")
        return created_calendar['id']
    except HttpError as error:
        print(f"FAILED to create calendar '{summary}': {error}")
        return None

def list_events(service, calendar_id='primary', max_results=10):
    """
    Lists the next few upcoming events on the specified calendar.
    """
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print(f"Getting the next {max_results} upcoming events for calendar: {calendar_id}")
        events_result = service.events().list(calendarId=calendar_id, timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            print('No upcoming events found.')
            return

        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(f"{start} - {event['summary']}")
    except HttpError as error:
        print(f"An error occurred: {error}")

def get_upcoming_events(service, calendar_id='primary', max_results=10):
    """
    Returns a list of upcoming events as dictionaries.
    Each event has: summary, start, end, description
    """
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        result = []
        for event in events:
            result.append({
                'summary': event.get('summary', 'No title'),
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'description': event.get('description', '')
            })
        return result
    except HttpError as error:
        print(f"Error fetching events: {error}")
        return []

def get_all_upcoming_events(service, max_results_per_calendar=10):
    """
    Returns events from all calendars as a dict: {calendar_name: [events]}
    """
    all_events = {}
    cal_map = get_calendar_map(service)

    for cal_name, cal_id in cal_map.items():
        events = get_upcoming_events(service, cal_id, max_results_per_calendar)
        if events:
            all_events[cal_name] = events

    return all_events

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Google Calendar Agent Tool")
    parser.add_argument("--summary", help="Event title", required=False)
    parser.add_argument("--start", help="Start time (ISO 8601: YYYY-MM-DDTHH:MM:SS)", required=False)
    parser.add_argument("--end", help="End time (ISO 8601: YYYY-MM-DDTHH:MM:SS)", required=False)
    parser.add_argument("--description", help="Event description", default="")
    parser.add_argument("--calendar-id", help="ID of the calendar to add event to (default: primary)", default="primary")
    parser.add_argument("--recurrence", help="RRULE string (e.g., 'RRULE:FREQ=WEEKLY;BYDAY=MO')", required=False)
    parser.add_argument("--list-calendars", action="store_true", help="List all available calendars")
    parser.add_argument("--list-events", action="store_true", help="List upcoming events for the calendar")
    parser.add_argument("--create-calendar", help="Name of new calendar to create")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")

    args = parser.parse_args()

    # Authenticate
    service = get_service()

    # CLI Mode
    if args.create_calendar:
        create_calendar(service, args.create_calendar)
        return

    if args.list_calendars:
        list_calendars(service)
        return

    if args.list_events:
        list_events(service, args.calendar_id)
        return

    if args.summary and args.start and args.end:
        print(f"Adding event: {args.summary}...")
        add_event(service, args.summary, args.start, args.end, args.description, args.calendar_id, args.recurrence)
        return

    # Interactive Mode (Default if no args)
    print("--- Google Calendar Tool ---")
    print("Authentication successful.\n")
    print("Usage: python calendar_client.py --summary ...")

if __name__ == "__main__":
    main()
