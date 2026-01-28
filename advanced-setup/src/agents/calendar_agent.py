"""CalendarAgent - handles calendar scheduling and queries.

Sends email responses directly after completing tasks.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.adk import Agent

from src.agents.tools.calendar_tools import (
    create_calendar_event,
    list_calendars,
    query_calendar_events,
)
from src.agents.tools.email_tools import send_email_response
from src.config import get_config


def get_calendar_instruction(ctx) -> str:
    """Generate calendar instruction with current date/time."""
    config = get_config()
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    return f"""You are a calendar assistant specializing in schedule management.

CURRENT DATE/TIME: {now.strftime("%A, %B %d, %Y at %I:%M %p")} ({config.timezone})
TODAY IS: {now.strftime("%A, %B %d, %Y")}

Your capabilities:
- Create new calendar events with specific times, durations, and recurrence
- Query upcoming events across all calendars or specific ones
- List available calendars

When creating events:
- Parse natural language dates and times carefully relative to TODAY shown above
- Default to 1-hour duration if not specified
- Use the user's timezone ({config.timezone})

When querying events:
- Present events in a clear, chronological format
- Group by calendar if showing multiple calendars
- Include relevant details like time and description
- "Tomorrow" means {(now + timedelta(days=1)).strftime("%A, %B %d, %Y")}

IMPORTANT: After completing the task, you MUST call send_email_response to deliver the results to the user. Be friendly and concise in your email.
"""


_config = get_config()

calendar_agent = Agent(
    name="CalendarAgent",
    model=_config.gemini_model,
    instruction=get_calendar_instruction,
    tools=[
        create_calendar_event,
        query_calendar_events,
        list_calendars,
        send_email_response,  # Sub-agents send their own emails in ADK
    ],
    output_key="calendar_results",
)
