"""CalendarAgent - handles calendar scheduling and queries.

Returns results to RouterAgent for email delivery.
"""

from google.adk import Agent

from src.agents.tools.calendar_tools import (
    create_calendar_event,
    list_calendars,
    query_calendar_events,
)
from src.agents.tools.email_tools import send_email_response
from src.config import get_config

CALENDAR_AGENT_INSTRUCTION = """You are a calendar assistant specializing in schedule management.

Your capabilities:
- Create new calendar events with specific times, durations, and recurrence
- Query upcoming events across all calendars or specific ones
- List available calendars

When creating events:
- Parse natural language dates and times carefully
- Default to 1-hour duration if not specified
- Use the user's timezone (already configured)

When querying events:
- Present events in a clear, chronological format
- Group by calendar if showing multiple calendars
- Include relevant details like time and description

IMPORTANT: After completing the task, you MUST call send_email_response to deliver the results to the user. Be friendly and concise in your email.
"""

_config = get_config()

calendar_agent = Agent(
    name="CalendarAgent",
    model=_config.gemini_model,
    instruction=CALENDAR_AGENT_INSTRUCTION,
    tools=[
        create_calendar_event,
        query_calendar_events,
        list_calendars,
        send_email_response,  # Sub-agents send their own emails in ADK
    ],
    output_key="calendar_results",
)
