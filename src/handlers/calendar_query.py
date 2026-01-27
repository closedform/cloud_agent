"""Calendar query handler - answers questions about calendar events."""

from src.clients import calendar as calendar_client
from src.clients.email import send_email
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services


@register_handler("calendar_query")
def handle_calendar_query(task: Task, config: Config, services: Services) -> None:
    """Handle calendar query tasks."""
    query = task.body.strip()
    reply_to = task.reply_to

    if not query:
        print("  No query in task body")
        return

    if not reply_to:
        print("  No reply_to address")
        return

    print(f"  Calendar query: {query[:80]}...")

    # Fetch calendar events
    try:
        if not services.calendar_service:
            raise Exception("Calendar service not initialized")

        all_events = calendar_client.get_all_upcoming_events(
            services.calendar_service, max_results_per_calendar=20
        )

        events_context = f"Available calendars: {list(services.calendars.keys())}\n\n"
        for cal_name, events in all_events.items():
            events_context += f"\n=== {cal_name} ===\n"
            for event in events:
                events_context += (
                    f"- {event['summary']} | Start: {event['start']} | End: {event['end']}\n"
                )
                if event.get("description"):
                    events_context += f"  Description: {event['description']}\n"

        if not all_events:
            events_context += "No upcoming events found."

    except Exception as e:
        print(f"  Calendar fetch error: {e}")
        send_email(
            to_address=reply_to,
            subject="Calendar Query Error",
            body=f"Sorry, I couldn't access the calendar: {e}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        return

    prompt = f"""You are a calendar assistant. Answer the user's question based on the calendar data below.

USER QUESTION: {query}

CALENDAR DATA:
{events_context}

Provide a clear, helpful answer. Include relevant dates and times."""

    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=[prompt],
        )

        result = response.text
        subject_line = query.split("\n")[0][:50]

        send_email(
            to_address=reply_to,
            subject=f"Re: {subject_line}",
            body=result,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"  Response sent to {reply_to}")

    except Exception as e:
        print(f"  Calendar query error: {e}")
        send_email(
            to_address=reply_to,
            subject="Calendar Query Error",
            body=f"Sorry, I encountered an error: {e}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
