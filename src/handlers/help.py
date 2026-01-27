"""Help handler - answers questions about the system."""

from src.clients.email import send_email
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services

SYSTEM_INFO = """You are a helpful assistant for the Cloud Agent system. Answer questions about what this system can do.

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


@register_handler("help")
def handle_help(task: Task, config: Config, services: Services) -> None:
    """Handle help/query tasks about the system itself."""
    question = task.subject.strip()
    reply_to = task.reply_to

    if not reply_to:
        print("  No reply_to address for help")
        return

    print(f"  Help query: {question[:50]}...")

    prompt = f"""{SYSTEM_INFO}

USER QUESTION: {question}

Provide a helpful, concise answer. Be friendly but direct. If they're asking about a specific feature, give them the exact format to use with an example."""

    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=[prompt],
        )

        result = response.text

        send_email(
            to_address=reply_to,
            subject=f"Re: {question[:50]}",
            body=result,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"  Help response sent to {reply_to}")

    except Exception as e:
        print(f"  Help error: {e}")
        send_email(
            to_address=reply_to,
            subject="Help Error",
            body=f"Sorry, I encountered an error: {e}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
