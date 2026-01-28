"""SystemAgent - handles status and help requests.

Sends email responses directly after completing tasks.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.adk import Agent


def get_system_status() -> dict[str, Any]:
    """Get current system status.

    Returns:
        Dictionary with system health information.
    """
    from src.agents.tools._context import get_services
    from src.config import get_config

    config = get_config()
    services = get_services()
    tz = ZoneInfo(config.timezone)

    status = {
        "status": "operational",
        "timestamp": datetime.now(tz).isoformat(),
        "components": {
            "gemini": "connected" if services and services.gemini_client else "disconnected",
            "calendar": "connected" if services and services.calendar_service else "disconnected",
            "email": "configured" if config.email_user else "not configured",
        },
    }

    # Check for pending reminders
    if config.reminders_file.exists():
        import json
        try:
            with open(config.reminders_file, "r") as f:
                reminders = json.load(f)
            status["pending_reminders"] = len(reminders)
        except Exception:
            status["pending_reminders"] = "unknown"

    # Check calendars
    if services and services.calendars:
        status["calendars_loaded"] = len(services.calendars)

    return status


def get_capabilities_list() -> dict[str, Any]:
    """Get list of all available capabilities.

    Returns:
        Dictionary describing system capabilities.
    """
    return {
        "capabilities": [
            {
                "category": "Calendar",
                "actions": [
                    "Schedule events (e.g., 'Schedule a meeting tomorrow at 2pm')",
                    "Query calendar (e.g., 'What's on my calendar this week?')",
                    "List calendars (e.g., 'What calendars do I have?')",
                ],
            },
            {
                "category": "Lists",
                "actions": [
                    "Add to list (e.g., 'Add Inception to my movie list')",
                    "View list (e.g., 'Show my grocery list')",
                    "Remove from list (e.g., 'Remove milk from groceries')",
                    "List all lists (e.g., 'What lists do I have?')",
                ],
            },
            {
                "category": "Todos",
                "actions": [
                    "Add todo (e.g., 'Add todo: call mom')",
                    "Add todo with due date (e.g., 'Todo: submit report, due Friday')",
                    "View todos (e.g., 'Show my todos')",
                    "Complete todo (e.g., 'Done with call mom')",
                ],
            },
            {
                "category": "Reminders",
                "actions": [
                    "Set reminder (e.g., 'Remind me to take medicine at 9pm')",
                    "Set future reminder (e.g., 'Remind me about the meeting tomorrow at 3pm')",
                ],
            },
            {
                "category": "Automation Rules",
                "actions": [
                    "Weekly schedule (e.g., 'Send me my schedule every Sunday')",
                    "Event reminders (e.g., 'Remind me 3 days before any dentist appointment')",
                    "View rules (e.g., 'What automations do I have?')",
                    "Delete rules (e.g., 'Stop the weekly schedule')",
                ],
            },
            {
                "category": "Research",
                "actions": [
                    "Web search (e.g., 'Research the best hiking trails in Colorado')",
                    "Current events (e.g., 'What's happening with...?')",
                ],
            },
            {
                "category": "Diary",
                "actions": [
                    "Query past activity (e.g., 'What did I do last week?')",
                    "Find past events (e.g., 'When did I finish the report?')",
                ],
            },
            {
                "category": "System",
                "actions": [
                    "Check status (e.g., 'Status' or 'Are you working?')",
                    "Get help (e.g., 'Help' or 'What can you do?')",
                ],
            },
        ],
        "tip": "Just send an email with your request - I'll figure out what you need!",
    }


SYSTEM_AGENT_INSTRUCTION = """You are a system assistant providing status and help information.

Your capabilities:
- Check system status and health
- Explain available capabilities and how to use them

When asked about status:
- Show component health (Gemini, Calendar, Email)
- Include relevant metrics like pending reminders

When asked for help:
- List capabilities organized by category
- Provide example commands for each

IMPORTANT: After completing the task, you MUST call send_email_response to deliver the results to the user. Be friendly and concise in your email.
"""

from src.agents.tools.email_tools import send_email_response
from src.config import get_config

_config = get_config()

system_agent = Agent(
    name="SystemAgent",
    model=_config.gemini_model,
    instruction=SYSTEM_AGENT_INSTRUCTION,
    tools=[
        get_system_status,
        get_capabilities_list,
        send_email_response,  # Sub-agents send their own emails in ADK
    ],
    output_key="system_results",
)
