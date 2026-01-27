"""Status handler - reports agent health and configuration."""

import json

from src.clients.email import send_email
from src.config import Config
from src.handlers.base import register_handler
from src.models import Task
from src.services import Services


@register_handler("status")
def handle_status(task: Task, config: Config, services: Services) -> None:
    """Handle status request - report agent configuration and API status."""
    reply_to = task.reply_to

    if not reply_to:
        print("  No reply_to address")
        return

    print("  Generating status report...")

    status_lines = []
    status_lines.append("=== Cloud Agent Status ===\n")

    # Model configuration
    status_lines.append("CONFIGURATION")
    status_lines.append(f"  Main model: {config.gemini_model}")
    status_lines.append(f"  Research model: {config.gemini_research_model}")
    status_lines.append(f"  Calendars loaded: {len(services.calendars)}")
    status_lines.append(f"  Calendar names: {', '.join(services.calendars.keys())}")
    status_lines.append("")

    # Test API and get rate limit info
    status_lines.append("API STATUS")
    try:
        # Make a minimal test request
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=["Say 'ok' and nothing else."],
        )
        status_lines.append(f"  {config.gemini_model}: OK")

        # Try to get usage metadata if available
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            status_lines.append(f"  Test request tokens: {getattr(um, 'total_token_count', 'N/A')}")

    except Exception as e:
        status_lines.append(f"  {config.gemini_model}: ERROR - {e}")

    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_research_model,
            contents=["Say 'ok' and nothing else."],
        )
        status_lines.append(f"  {config.gemini_research_model}: OK")
    except Exception as e:
        status_lines.append(f"  {config.gemini_research_model}: ERROR - {e}")

    status_lines.append("")

    # Recent processed tasks
    status_lines.append("RECENT TASKS (last 10)")
    try:
        processed_files = sorted(config.processed_dir.glob("task_*.json"), reverse=True)[:10]
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
        pending_files = list(config.input_dir.glob("task_*.json"))
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
        body=status_report,
        email_user=config.email_user,
        email_pass=config.email_pass,
        smtp_server=config.smtp_server,
        smtp_port=config.smtp_port,
    )
    print(f"  Status sent to {reply_to}")
