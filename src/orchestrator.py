"""Orchestrator - the brain of the agent.

Watches the inputs/ folder for task files and routes them to appropriate handlers.
Supports: scheduling, research, calendar queries.
"""

import os
import json
import time
import shutil
from pathlib import Path
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from dotenv import load_dotenv

from src.clients import calendar as calendar_client
from src.clients.email import send_email

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")

INPUT_DIR = Path("inputs")
PROCESSED_DIR = Path("processed")

if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY not found. Please set it in .env")
    exit(1)

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize Calendar service and map
print("Loading calendars...")
try:
    calendar_service = calendar_client.get_service()
    CALENDARS = calendar_client.get_calendar_map(calendar_service)
    if "primary" not in CALENDARS:
        CALENDARS["primary"] = "primary"
    print(f"Loaded {len(CALENDARS)} calendars: {list(CALENDARS.keys())}")
except Exception as e:
    print(f"WARNING: Could not load calendars ({e}). Using fallback.")
    CALENDARS = {"primary": "primary"}
    calendar_service = None

DEFAULT_CALENDAR = "primary"


# =============================================================================
# HANDLERS
# =============================================================================

def handle_schedule(task: dict):
    """Handle calendar scheduling tasks."""
    body = task.get("body", "")
    subject = task.get("subject", "")
    attachments = task.get("attachments", [])

    # Build content for Gemini
    content = [build_schedule_prompt()]

    # Add text content
    if body.strip():
        content.append(f"Context from email subject: {subject}\n\n{body}")

    # Add image attachments
    for attachment in attachments:
        filepath = INPUT_DIR / attachment
        if filepath.exists() and filepath.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
            with open(filepath, "rb") as f:
                image_bytes = f.read()
            mime = "image/png" if filepath.suffix.lower() == ".png" else "image/jpeg"
            content.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))

    # Get Gemini response
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=content,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        response_text = response.text
        if "```json" in response_text:
            response_text = response_text.replace("```json", "").replace("```", "")

        data = json.loads(response_text)
        if not data:
            print("  No event found in task.")
            return

        events = data if isinstance(data, list) else [data]

        for event in events:
            if event.get('confidence') == 'Low':
                print(f"  Skipping low confidence: {event.get('summary')}")
                continue

            create_calendar_event(event)

    except Exception as e:
        print(f"  Schedule error: {e}")


def handle_research(task: dict):
    """Handle research tasks."""
    query = task.get("body", "").strip()
    reply_to = task.get("reply_to", "")

    if not query:
        print("  No query in task body")
        return

    if not reply_to:
        print("  No reply_to address")
        return

    print(f"  Researching: {query[:80]}...")

    prompt = f"""You are a research assistant. Answer the following query thoroughly and concisely.

Query: {query}

Use web search to find current, accurate information. Provide a well-structured response with key facts and insights."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())]
            )
        )

        result = response.text
        subject_line = query.split('\n')[0][:50]

        send_email(
            to_address=reply_to,
            subject=f"Re: {subject_line}",
            body=result
        )
        print(f"  Response sent to {reply_to}")

    except Exception as e:
        print(f"  Research error: {e}")
        send_email(
            to_address=reply_to,
            subject="Research Error",
            body=f"Sorry, I encountered an error: {e}"
        )


def handle_calendar_query(task: dict):
    """Handle calendar query tasks."""
    query = task.get("body", "").strip()
    reply_to = task.get("reply_to", "")

    if not query:
        print("  No query in task body")
        return

    if not reply_to:
        print("  No reply_to address")
        return

    print(f"  Calendar query: {query[:80]}...")

    # Fetch calendar events
    try:
        if not calendar_service:
            raise Exception("Calendar service not initialized")

        all_events = calendar_client.get_all_upcoming_events(calendar_service, max_results_per_calendar=20)

        events_context = f"Available calendars: {list(CALENDARS.keys())}\n\n"
        for cal_name, events in all_events.items():
            events_context += f"\n=== {cal_name} ===\n"
            for event in events:
                events_context += f"- {event['summary']} | Start: {event['start']} | End: {event['end']}\n"
                if event.get('description'):
                    events_context += f"  Description: {event['description']}\n"

        if not all_events:
            events_context += "No upcoming events found."

    except Exception as e:
        print(f"  Calendar fetch error: {e}")
        send_email(
            to_address=reply_to,
            subject="Calendar Query Error",
            body=f"Sorry, I couldn't access the calendar: {e}"
        )
        return

    prompt = f"""You are a calendar assistant. Answer the user's question based on the calendar data below.

USER QUESTION: {query}

CALENDAR DATA:
{events_context}

Provide a clear, helpful answer. Include relevant dates and times."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt]
        )

        result = response.text
        subject_line = query.split('\n')[0][:50]

        send_email(
            to_address=reply_to,
            subject=f"Re: {subject_line}",
            body=result
        )
        print(f"  Response sent to {reply_to}")

    except Exception as e:
        print(f"  Calendar query error: {e}")
        send_email(
            to_address=reply_to,
            subject="Calendar Query Error",
            body=f"Sorry, I encountered an error: {e}"
        )


# =============================================================================
# HELPERS
# =============================================================================

def build_schedule_prompt() -> str:
    """Build the system prompt for calendar scheduling."""
    return f"""You are an intelligent calendar assistant.
I will provide an email body, text, or image.

Available calendars: {list(CALENDARS.keys())}

Extract event details and return JSON:
{{
  "summary": "Short title",
  "start": "ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
  "end": "ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
  "description": "Any context",
  "calendar": "calendar_name or primary",
  "recurrence": "RRULE:..." or null,
  "confidence": "Low/Medium/High"
}}

Notes:
- Match calendar names if possible, default to "primary"
- For recurring events, generate valid RRULE strings
- Current year is 2026
"""


def create_calendar_event(event: dict):
    """Create a calendar event from parsed data."""
    cal_name = event.get('calendar', DEFAULT_CALENDAR).lower()

    # Fuzzy match calendar name
    target_cal_id = CALENDARS.get(cal_name)
    if not target_cal_id:
        for key in CALENDARS:
            if cal_name in key or key in cal_name:
                target_cal_id = CALENDARS[key]
                cal_name = key
                break

    # Create calendar if not found
    if not target_cal_id:
        print(f"  Calendar '{cal_name}' not found. Creating...")
        try:
            new_id = calendar_client.create_calendar(calendar_service, event.get('calendar', cal_name))
            if new_id:
                CALENDARS[cal_name.lower()] = new_id
                target_cal_id = new_id
        except Exception as e:
            print(f"  Failed to create calendar: {e}")
            target_cal_id = CALENDARS[DEFAULT_CALENDAR]

    print(f"  Creating: {event['summary']} -> {cal_name}")

    try:
        calendar_client.add_event(
            calendar_service,
            summary=event.get('summary', 'New Event'),
            start_time_iso=event.get('start', ''),
            end_time_iso=event.get('end', ''),
            description=event.get('description', ''),
            calendar_id=target_cal_id,
            recurrence=event.get('recurrence')
        )
    except Exception as e:
        print(f"  Failed to create event: {e}")


def process_task(task_file: Path):
    """Process a single task file."""
    print(f"Processing: {task_file.name}")

    try:
        with open(task_file, "r") as f:
            task = json.load(f)

        intent = task.get("intent", "unknown")

        if intent == "schedule":
            handle_schedule(task)
        elif intent == "research":
            handle_research(task)
        elif intent == "calendar_query":
            handle_calendar_query(task)
        else:
            print(f"  Unknown intent: {intent}")

    except Exception as e:
        print(f"  Error processing task: {e}")


def cleanup_task(task_file: Path):
    """Move task file and attachments to processed folder."""
    try:
        # Read task to get attachments
        with open(task_file, "r") as f:
            task = json.load(f)

        # Move attachments
        for attachment in task.get("attachments", []):
            src = INPUT_DIR / attachment
            if src.exists():
                shutil.move(str(src), str(PROCESSED_DIR / attachment))

        # Move task file
        shutil.move(str(task_file), str(PROCESSED_DIR / task_file.name))

    except Exception as e:
        print(f"  Cleanup error: {e}")


def main():
    print(f"Orchestrator started. Watching {INPUT_DIR.absolute()}...")

    INPUT_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)

    while True:
        # Find task files
        task_files = sorted(INPUT_DIR.glob("task_*.json"))

        for task_file in task_files:
            process_task(task_file)
            cleanup_task(task_file)

        time.sleep(5)


if __name__ == "__main__":
    main()
