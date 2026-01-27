"""Reminder handler - creates and manages scheduled reminders."""

import json
import threading
from datetime import datetime

from google.genai import types

from src.clients.email import send_email
from src.config import Config
from src.handlers.base import register_handler
from src.models import Reminder, Task
from src.services import Services


def send_reminder_email(
    reminder_id: str,
    message: str,
    reply_to: str,
    created_at: str,
    config: Config,
) -> None:
    """Send a reminder email and remove it from storage."""
    try:
        send_email(
            to_address=reply_to,
            subject=message,
            body=f"This is your reminder: {message}\n\nOriginally set: {created_at}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"Reminder fired: {message[:30]}... -> {reply_to}")

        # Remove from reminders.json
        if config.reminders_file.exists():
            with open(config.reminders_file, "r") as f:
                reminders = json.load(f)
            reminders = [r for r in reminders if r.get("id") != reminder_id]
            with open(config.reminders_file, "w") as f:
                json.dump(reminders, f, indent=2)

    except Exception as e:
        print(f"Error sending reminder: {e}")


def schedule_reminder(reminder: Reminder, config: Config) -> None:
    """Schedule a reminder using threading.Timer."""
    try:
        reminder_time = datetime.fromisoformat(reminder.datetime)
        now = datetime.now()
        delay = (reminder_time - now).total_seconds()

        if delay <= 0:
            # Already past due, send immediately
            send_reminder_email(
                reminder.id,
                reminder.message,
                reminder.reply_to,
                reminder.created_at,
                config,
            )
        else:
            # Schedule for later
            timer = threading.Timer(
                delay,
                send_reminder_email,
                args=[
                    reminder.id,
                    reminder.message,
                    reminder.reply_to,
                    reminder.created_at,
                    config,
                ],
            )
            timer.daemon = True
            timer.start()
            print(f"  Scheduled reminder in {delay:.0f}s: {reminder.message[:30]}...")

    except Exception as e:
        print(f"Error scheduling reminder: {e}")


def load_existing_reminders(config: Config) -> None:
    """Load and schedule any existing reminders from file."""
    if not config.reminders_file.exists():
        return

    try:
        with open(config.reminders_file, "r") as f:
            reminders_data = json.load(f)

        if reminders_data:
            print(f"Loading {len(reminders_data)} existing reminder(s)...")
            for reminder_dict in reminders_data:
                reminder = Reminder.from_dict(reminder_dict)
                schedule_reminder(reminder, config)

    except Exception as e:
        print(f"Error loading reminders: {e}")


@register_handler("reminder")
def handle_reminder(task: Task, config: Config, services: Services) -> None:
    """Handle reminder creation tasks."""
    reply_to = task.reply_to
    classification = task.classification or {}

    if not reply_to:
        print("  No reply_to address for reminder")
        return

    # Get reminder details from classification
    reminder_message = classification.get("reminder_message")
    reminder_time = classification.get("reminder_time")

    if not reminder_message or not reminder_time:
        # Need to re-parse if classification didn't extract details
        subject = task.subject
        body = task.body

        prompt = f"""Parse this reminder request and extract the details.

Subject: {subject}
Body: {body}

Current date/time: {datetime.now().strftime("%Y-%m-%d %H:%M")} (timezone: {config.timezone})

Return JSON with:
{{
  "message": "The reminder message/subject line",
  "datetime": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS)"
}}"""

        try:
            response = services.gemini_client.models.generate_content(
                model=config.gemini_model,
                contents=[prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
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
                body=f"Sorry, I couldn't understand your reminder request: {e}",
                email_user=config.email_user,
                email_pass=config.email_pass,
                smtp_server=config.smtp_server,
                smtp_port=config.smtp_port,
            )
            return

    if not reminder_message or not reminder_time:
        send_email(
            to_address=reply_to,
            subject="Reminder Not Understood",
            body="Sorry, I couldn't parse your reminder. Try something like: 'Remind me to meet with Einstein tomorrow at 3pm'",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        return

    print(f"  Setting reminder: {reminder_message[:30]}... at {reminder_time}")

    try:
        # Load existing reminders
        reminders = []
        if config.reminders_file.exists():
            with open(config.reminders_file, "r") as f:
                reminders = json.load(f)

        # Create new reminder
        reminder = Reminder.create(
            message=reminder_message,
            reminder_datetime=reminder_time,
            reply_to=reply_to,
            task_id=task.id,
        )
        reminders.append(reminder.to_dict())

        # Save reminders
        with open(config.reminders_file, "w") as f:
            json.dump(reminders, f, indent=2)

        # Schedule the reminder
        schedule_reminder(reminder, config)

        # Confirm to user
        send_email(
            to_address=reply_to,
            subject=f"Reminder Set: {reminder_message[:50]}",
            body=f"I'll remind you about: {reminder_message}\n\nScheduled for: {reminder_time}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"  Reminder set for {reminder_time} -> {reply_to}")

    except Exception as e:
        print(f"  Reminder error: {e}")
        send_email(
            to_address=reply_to,
            subject="Reminder Error",
            body=f"Sorry, I encountered an error setting your reminder: {e}",
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
