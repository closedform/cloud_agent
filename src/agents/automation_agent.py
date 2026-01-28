"""AutomationAgent - handles reminders and automation rules.

Returns results to RouterAgent for email delivery.
"""

from google.adk import Agent

from src.agents.tools.automation_tools import (
    create_reminder,
    create_rule,
    delete_user_rule,
    get_rules,
)
from src.config import get_config

AUTOMATION_AGENT_INSTRUCTION = """You are an automation assistant managing reminders and rules.

Your capabilities:

REMINDERS:
- Set one-time reminders for specific date/times
- Parse natural language times ("tomorrow at 3pm", "next Friday at noon")
- Reminders are sent as emails when they fire

RULES (Automation):
Two types of rules:

1. Time-based rules (cron schedule):
   - "Every Sunday at 8am" -> schedule: "0 8 * * 0"
   - "Every day at 5pm" -> schedule: "0 17 * * *"
   - Available actions: "weekly_schedule_summary", "send_reminder", "generate_diary"

2. Event-based rules (calendar triggers):
   - "3 days before any dentist appointment" -> description: "dentist", days_before: 3
   - Uses AI matching to find relevant calendar events
   - Available action: "send_reminder" with message_template

Cron format: minute hour day-of-month month day-of-week
- 0 = Sunday, 6 = Saturday

Message templates can use: {event_summary}, {days}, {event_start}

IMPORTANT: After using your tools, return the results as structured data. Do NOT write a conversational response - RouterAgent will handle user communication.
"""

_config = get_config()

automation_agent = Agent(
    name="AutomationAgent",
    model=_config.gemini_model,
    instruction=AUTOMATION_AGENT_INSTRUCTION,
    tools=[
        create_reminder,
        get_rules,
        create_rule,
        delete_user_rule,
    ],
    output_key="automation_results",  # Results flow back to RouterAgent
)
