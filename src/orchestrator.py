"""Orchestrator - the brain of the agent.

Watches the inputs/ folder for task files and routes them to appropriate handlers.
Supports: scheduling, research, calendar queries.
"""

import os
import json
import time
import shutil
import threading
from pathlib import Path
from datetime import datetime
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
GEMINI_RESEARCH_MODEL = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-2.5-flash")  # Has free Google Search

INPUT_DIR = Path("inputs")
PROCESSED_DIR = Path("processed")
REMINDERS_FILE = Path("reminders.json")

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
        # Use research model (2.5 Flash) for free Google Search grounding
        response = client.models.generate_content(
            model=GEMINI_RESEARCH_MODEL,
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
        print(f"  Response sent to {reply_to} (model: {GEMINI_RESEARCH_MODEL})")

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


def handle_status(task: dict):
    """Handle status request - report agent configuration and API status."""
    reply_to = task.get("reply_to", "")

    if not reply_to:
        print("  No reply_to address")
        return

    print(f"  Generating status report...")

    status_lines = []
    status_lines.append("=== Cloud Agent Status ===\n")

    # Model configuration
    status_lines.append("CONFIGURATION")
    status_lines.append(f"  Main model: {GEMINI_MODEL}")
    status_lines.append(f"  Research model: {GEMINI_RESEARCH_MODEL}")
    status_lines.append(f"  Calendars loaded: {len(CALENDARS)}")
    status_lines.append(f"  Calendar names: {', '.join(CALENDARS.keys())}")
    status_lines.append("")

    # Test API and get rate limit info
    status_lines.append("API STATUS")
    try:
        # Make a minimal test request
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=["Say 'ok' and nothing else."]
        )
        status_lines.append(f"  {GEMINI_MODEL}: OK")

        # Try to get usage metadata if available
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            um = response.usage_metadata
            status_lines.append(f"  Test request tokens: {getattr(um, 'total_token_count', 'N/A')}")

    except Exception as e:
        status_lines.append(f"  {GEMINI_MODEL}: ERROR - {e}")

    try:
        response = client.models.generate_content(
            model=GEMINI_RESEARCH_MODEL,
            contents=["Say 'ok' and nothing else."]
        )
        status_lines.append(f"  {GEMINI_RESEARCH_MODEL}: OK")
    except Exception as e:
        status_lines.append(f"  {GEMINI_RESEARCH_MODEL}: ERROR - {e}")

    status_lines.append("")

    # Recent processed tasks
    status_lines.append("RECENT TASKS (last 10)")
    try:
        processed_files = sorted(PROCESSED_DIR.glob("task_*.json"), reverse=True)[:10]
        if processed_files:
            for f in processed_files:
                with open(f, "r") as fp:
                    t = json.load(fp)
                status_lines.append(f"  [{t.get('intent')}] {t.get('created_at', 'unknown')}")
        else:
            status_lines.append("  No processed tasks yet")
    except Exception as e:
        status_lines.append(f"  Error reading tasks: {e}")

    status_lines.append("")

    # Pending tasks
    status_lines.append("PENDING TASKS")
    try:
        pending_files = list(INPUT_DIR.glob("task_*.json"))
        status_lines.append(f"  Count: {len(pending_files)}")
    except Exception as e:
        status_lines.append(f"  Error: {e}")

    status_lines.append("")
    status_lines.append("---")
    status_lines.append("View rate limits: https://aistudio.google.com")
    status_lines.append("Free tier: 15 RPM / 1500 RPD (Flash), 5 RPM / 500 RPD (Pro)")

    status_report = "\n".join(status_lines)

    send_email(
        to_address=reply_to,
        subject="Cloud Agent Status Report",
        body=status_report
    )
    print(f"  Status sent to {reply_to}")


def handle_reminder(task: dict):
    """Handle reminder creation tasks."""
    reply_to = task.get("reply_to", "")
    classification = task.get("classification", {})

    if not reply_to:
        print("  No reply_to address for reminder")
        return

    # Get reminder details from classification
    reminder_message = classification.get("reminder_message")
    reminder_time = classification.get("reminder_time")

    if not reminder_message or not reminder_time:
        # Need to re-parse if classification didn't extract details
        subject = task.get("subject", "")
        body = task.get("body", "")

        prompt = f"""Parse this reminder request and extract the details.

Subject: {subject}
Body: {body}

Current date/time: {datetime.now().strftime("%Y-%m-%d %H:%M")}

Return JSON with:
{{
  "message": "The reminder message/subject line",
  "datetime": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS)"
}}"""

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )

            response_text = response.text
            if "```json" in response_text:
                response_text = response_text.replace("```json", "").replace("```", "")

            data = json.loads(response_text)
            reminder_message = data.get("message")
            reminder_time = data.get("datetime")

        except Exception as e:
            print(f"  Reminder parse error: {e}")
            send_email(
                to_address=reply_to,
                subject="Reminder Error",
                body=f"Sorry, I couldn't understand your reminder request: {e}"
            )
            return

    if not reminder_message or not reminder_time:
        send_email(
            to_address=reply_to,
            subject="Reminder Not Understood",
            body="Sorry, I couldn't parse your reminder. Try something like: 'Remind me to meet with Einstein tomorrow at 3pm'"
        )
        return

    print(f"  Setting reminder: {reminder_message[:30]}... at {reminder_time}")

    try:
        # Load existing reminders
        reminders = []
        if REMINDERS_FILE.exists():
            with open(REMINDERS_FILE, "r") as f:
                reminders = json.load(f)

        # Add new reminder
        reminder = {
            "id": task.get("id", str(int(time.time() * 1000))),
            "message": reminder_message,
            "datetime": reminder_time,
            "reply_to": reply_to,
            "created_at": datetime.now().isoformat()
        }
        reminders.append(reminder)

        # Save reminders
        with open(REMINDERS_FILE, "w") as f:
            json.dump(reminders, f, indent=2)

        # Schedule the reminder
        schedule_reminder(reminder)

        # Confirm to user
        send_email(
            to_address=reply_to,
            subject=f"Reminder Set: {reminder_message[:50]}",
            body=f"I'll remind you about: {reminder_message}\n\nScheduled for: {reminder_time}"
        )
        print(f"  Reminder set for {reminder_time} -> {reply_to}")

    except Exception as e:
        print(f"  Reminder error: {e}")
        send_email(
            to_address=reply_to,
            subject="Reminder Error",
            body=f"Sorry, I encountered an error setting your reminder: {e}"
        )


def handle_help(task: dict):
    """Handle help/query tasks about the system itself."""
    question = task.get("subject", "").strip()
    reply_to = task.get("reply_to", "")

    if not reply_to:
        print("  No reply_to address for help")
        return

    print(f"  Help query: {question[:50]}...")

    system_info = """You are a helpful assistant for the Cloud Agent system. Answer questions about what this system can do.

SYSTEM CAPABILITIES:

1. SCHEDULE EVENTS
   Subject contains "schedule" or "appointment"
   Example: "Schedule dentist appointment"
   Body: "Dr. Smith next Tuesday at 2pm, should take about an hour"
   -> Creates a Google Calendar event

2. RESEARCH (with web search)
   Subject: "Research: <your-email>"
   Body: Your question
   Example Subject: "Research: me@example.com"
   Example Body: "What are the best practices for Python async?"
   -> Searches the web and emails you the answer

3. CALENDAR QUERIES
   Subject: "Calendar: <your-email>"
   Body: Your question about your schedule
   Example Subject: "Calendar: me@example.com"
   Example Body: "What do I have this week?"
   -> Checks your calendars and emails you the answer

4. REMINDERS
   Subject: "REMIND ME: <thing> @ <time> ON <date>"
   Example: "REMIND ME: meet with Einstein @ 3pm on friday"
   -> Sends you an email reminder at the specified time

5. STATUS CHECK
   Subject: "Status: <your-email>"
   -> Emails you a health report (API status, recent tasks, config)

6. HELP (this feature)
   Subject: Any question ending with "?" or starting with "how", "what", "help"
   Example: "What can you do?" or "How do I set a reminder?"
   -> Emails you helpful information

TIPS:
- All commands are sent via email to the agent's email address
- Only emails from allowed senders are processed
- The agent checks for new emails every minute
- Reminders are checked every 5 seconds once created
"""

    prompt = f"""{system_info}

USER QUESTION: {question}

Provide a helpful, concise answer. Be friendly but direct. If they're asking about a specific feature, give them the exact format to use with an example."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt]
        )

        result = response.text

        send_email(
            to_address=reply_to,
            subject=f"Re: {question[:50]}",
            body=result
        )
        print(f"  Help response sent to {reply_to}")

    except Exception as e:
        print(f"  Help error: {e}")
        send_email(
            to_address=reply_to,
            subject="Help Error",
            body=f"Sorry, I encountered an error: {e}"
        )


def send_reminder(reminder_id: str, message: str, reply_to: str, created_at: str):
    """Send a reminder email and remove it from storage."""
    try:
        send_email(
            to_address=reply_to,
            subject=message,
            body=f"This is your reminder: {message}\n\nOriginally set: {created_at}"
        )
        print(f"Reminder fired: {message[:30]}... -> {reply_to}")

        # Remove from reminders.json
        if REMINDERS_FILE.exists():
            with open(REMINDERS_FILE, "r") as f:
                reminders = json.load(f)
            reminders = [r for r in reminders if r.get("id") != reminder_id]
            with open(REMINDERS_FILE, "w") as f:
                json.dump(reminders, f, indent=2)

    except Exception as e:
        print(f"Error sending reminder: {e}")


def schedule_reminder(reminder: dict):
    """Schedule a reminder using threading.Timer."""
    try:
        reminder_time = datetime.fromisoformat(reminder["datetime"])
        now = datetime.now()
        delay = (reminder_time - now).total_seconds()

        if delay <= 0:
            # Already past due, send immediately
            send_reminder(
                reminder["id"],
                reminder["message"],
                reminder["reply_to"],
                reminder.get("created_at", "unknown")
            )
        else:
            # Schedule for later
            timer = threading.Timer(
                delay,
                send_reminder,
                args=[
                    reminder["id"],
                    reminder["message"],
                    reminder["reply_to"],
                    reminder.get("created_at", "unknown")
                ]
            )
            timer.daemon = True
            timer.start()
            print(f"  Scheduled reminder in {delay:.0f}s: {reminder['message'][:30]}...")

    except Exception as e:
        print(f"Error scheduling reminder: {e}")


def load_existing_reminders():
    """Load and schedule any existing reminders from file."""
    if not REMINDERS_FILE.exists():
        return

    try:
        with open(REMINDERS_FILE, "r") as f:
            reminders = json.load(f)

        if reminders:
            print(f"Loading {len(reminders)} existing reminder(s)...")
            for reminder in reminders:
                schedule_reminder(reminder)

    except Exception as e:
        print(f"Error loading reminders: {e}")


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


def classify_intent(task: dict) -> dict:
    """Use Gemini to classify the intent of an incoming task."""
    subject = task.get("subject", "")
    body = task.get("body", "")

    prompt = f"""Classify this email request. Return JSON with intent and any extracted data.

SUBJECT: {subject}
BODY: {body}

CURRENT DATE/TIME: {datetime.now().strftime("%Y-%m-%d %H:%M")} (use this to resolve relative times like "tomorrow", "next friday")

AVAILABLE INTENTS:
- "schedule": Create a calendar event (keywords: schedule, appointment, meeting, event)
- "research": Research a topic using web search (user wants information/research)
- "calendar_query": Question about existing calendar/schedule (what do I have, when is, am I free)
- "reminder": Set a reminder for later (remind me, don't forget, alert me)
- "status": Check system status (status, health, working)
- "help": Question about how to use this system (how do I, what can you, help)
- "unknown": Can't determine intent

Return JSON:
{{
  "intent": "one of the above",
  "summary": "brief description of what user wants",
  "reminder_time": "ISO datetime (YYYY-MM-DDTHH:MM:SS) if reminder, else null",
  "reminder_message": "reminder text if reminder, else null"
}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        response_text = response.text
        if "```json" in response_text:
            response_text = response_text.replace("```json", "").replace("```", "")

        return json.loads(response_text)

    except Exception as e:
        print(f"  Classification error: {e}")
        return {"intent": "unknown", "summary": str(e)}


def process_task(task_file: Path):
    """Process a single task file."""
    print(f"Processing: {task_file.name}")

    try:
        with open(task_file, "r") as f:
            task = json.load(f)

        # Classify intent using Gemini
        classification = classify_intent(task)
        intent = classification.get("intent", "unknown")
        print(f"  Intent: {intent} ({classification.get('summary', '')[:50]})")

        # Add classification data to task
        task["classification"] = classification

        if intent == "schedule":
            handle_schedule(task)
        elif intent == "research":
            handle_research(task)
        elif intent == "calendar_query":
            handle_calendar_query(task)
        elif intent == "status":
            handle_status(task)
        elif intent == "reminder":
            handle_reminder(task)
        elif intent == "help":
            handle_help(task)
        else:
            print(f"  Unknown intent, skipping")

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

    # Load and schedule any existing reminders
    load_existing_reminders()

    while True:
        # Find task files
        task_files = sorted(INPUT_DIR.glob("task_*.json"))

        for task_file in task_files:
            process_task(task_file)
            cleanup_task(task_file)

        time.sleep(5)


if __name__ == "__main__":
    main()
