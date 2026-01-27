"""Schedule handler - creates calendar events from email requests."""

import json

from google.genai import types

from src.clients import calendar as calendar_client
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services


def build_schedule_prompt(calendars: dict[str, str]) -> str:
    """Build the system prompt for calendar scheduling."""
    return f"""You are an intelligent calendar assistant.
I will provide an email body, text, or image.

Available calendars: {list(calendars.keys())}

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


def create_calendar_event(
    event: dict,
    config: Config,
    services: Services,
) -> None:
    """Create a calendar event from parsed data."""
    cal_name = event.get("calendar", config.default_calendar).lower()

    # Fuzzy match calendar name
    target_cal_id = services.calendars.get(cal_name)
    if not target_cal_id:
        for key in services.calendars:
            if cal_name in key or key in cal_name:
                target_cal_id = services.calendars[key]
                cal_name = key
                break

    # Create calendar if not found
    if not target_cal_id:
        print(f"  Calendar '{cal_name}' not found. Creating...")
        try:
            new_id = calendar_client.create_calendar(
                services.calendar_service,
                event.get("calendar", cal_name),
                timezone=config.timezone,
            )
            if new_id:
                services.calendars[cal_name.lower()] = new_id
                target_cal_id = new_id
        except Exception as e:
            print(f"  Failed to create calendar: {e}")
            target_cal_id = services.calendars[config.default_calendar]

    print(f"  Creating: {event['summary']} -> {cal_name}")

    try:
        calendar_client.add_event(
            services.calendar_service,
            summary=event.get("summary", "New Event"),
            start_time_iso=event.get("start", ""),
            end_time_iso=event.get("end", ""),
            description=event.get("description", ""),
            calendar_id=target_cal_id,
            recurrence=event.get("recurrence"),
            timezone=config.timezone,
        )
    except Exception as e:
        print(f"  Failed to create event: {e}")


@register_handler("schedule")
def handle_schedule(task: Task, config: Config, services: Services) -> None:
    """Handle calendar scheduling tasks."""
    body = task.body
    subject = task.subject
    attachments = task.attachments

    # Build content for Gemini
    content = [build_schedule_prompt(services.calendars)]

    # Add text content
    if body.strip():
        content.append(f"Context from email subject: {subject}\n\n{body}")

    # Add image attachments
    for attachment in attachments:
        filepath = config.input_dir / attachment
        if filepath.exists() and filepath.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
            with open(filepath, "rb") as f:
                image_bytes = f.read()
            mime = "image/png" if filepath.suffix.lower() == ".png" else "image/jpeg"
            content.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))

    # Get Gemini response
    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=content,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
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
            if event.get("confidence") == "Low":
                print(f"  Skipping low confidence: {event.get('summary')}")
                continue

            create_calendar_event(event, config, services)

    except Exception as e:
        print(f"  Schedule error: {e}")
