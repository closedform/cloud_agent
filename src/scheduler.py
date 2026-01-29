"""Scheduler for time-based and event-based rules.

Runs in a background thread, checking rules every 60 seconds.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter, CroniterBadCronError

from src.clients import calendar as calendar_client
from src.clients.email import (
    send_email,
    html_weekly_schedule,
    format_weather_html,
    format_calendar_html,
)
from src.config import Config
from src.weather import get_weekly_forecast, format_forecast_for_email
from src.diary import (
    DiaryEntry,
    get_reminders_in_range,
    get_week_bounds,
    get_week_id,
    save_diary_entry,
)
from src.identities import IDENTITIES
from src.rules import (
    Rule,
    cleanup_old_triggered,
    get_user_rules,
    is_event_triggered,
    load_rules_safe,
    mark_event_triggered,
    update_rule_last_fired,
)
from src.services import Services
from src.user_data import get_todos, load_user_data


def run_scheduler(
    config: Config,
    services: Services,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Main scheduler loop - runs in separate thread.

    Args:
        config: Application configuration.
        services: Initialized external services.
        shutdown_event: Optional event to signal shutdown.
    """
    print("Scheduler started")
    while True:
        # Check for shutdown
        if shutdown_event is not None and shutdown_event.is_set():
            print("Scheduler shutting down...")
            break

        try:
            check_time_rules(config, services)
            check_event_rules(config, services)
            check_weekly_diary(config, services)
            check_triggered_cleanup(config)
        except Exception as e:
            print(f"Scheduler error: {e}")

        # Use event wait for responsive shutdown, fall back to sleep
        if shutdown_event is not None:
            shutdown_event.wait(timeout=60)
        else:
            time.sleep(60)


def check_time_rules(config: Config, services: Services) -> None:
    """Check and fire time-based rules.

    Uses timezone-aware datetimes throughout for correct DST handling.
    croniter preserves timezone info when given an aware datetime.
    """
    rules_data = load_rules_safe(config)
    local_tz = ZoneInfo(config.timezone)
    now = datetime.now(local_tz)

    for email, rules in rules_data.items():
        for rule_dict in rules:
            rule = Rule.from_dict(rule_dict)
            if rule.type != "time" or not rule.enabled or not rule.schedule:
                continue

            try:
                # croniter preserves timezone when given aware datetime
                # Start from 1 minute ago to find if current minute should fire
                cron = croniter(rule.schedule, now - timedelta(minutes=1))
                next_fire = cron.get_next(datetime)  # Returns aware datetime

                # Fire if next scheduled time is within this minute
                minute_start = now.replace(second=0, microsecond=0)
                minute_end = minute_start + timedelta(minutes=1)
                if minute_start <= next_fire < minute_end:
                    # Check last_fired to prevent double-firing
                    # Use 55 seconds (just under 60s interval) to allow every-minute cron jobs
                    if rule.last_fired:
                        try:
                            last = datetime.fromisoformat(rule.last_fired)
                            # Ensure last_fired is timezone-aware for comparison
                            if last.tzinfo is None:
                                last = last.replace(tzinfo=local_tz)
                            if (now - last).total_seconds() < 55:
                                continue
                        except (ValueError, TypeError):
                            # Invalid last_fired format - proceed with firing
                            pass

                    print(f"Firing time rule {rule.id} for {email}: {rule.action}")
                    execute_action(rule, email, config, services)
                    update_rule_last_fired(email, rule.id, config)

            except CroniterBadCronError as e:
                print(f"Invalid cron expression in rule {rule.id}: {rule.schedule!r} - {e}")
            except Exception as e:
                print(f"Error checking time rule {rule.id}: {e}")


def check_event_rules(config: Config, services: Services) -> None:
    """Check and fire event-based rules using AI matching."""
    if not services.calendar_service:
        return

    rules_data = load_rules_safe(config)
    local_tz = ZoneInfo(config.timezone)

    # Get events for next 30 days
    try:
        all_events = calendar_client.get_all_upcoming_events(
            services.calendar_service, max_results_per_calendar=50
        )
    except Exception as e:
        print(f"Scheduler: Could not fetch calendar events: {e}")
        return

    # Flatten events with their dates
    events_list: list[dict[str, Any]] = []
    for cal_name, events in all_events.items():
        for event in events:
            event["calendar"] = cal_name
            events_list.append(event)

    for email, rules in rules_data.items():
        for rule_dict in rules:
            rule = Rule.from_dict(rule_dict)
            if rule.type != "event" or not rule.enabled or not rule.description:
                continue

            days_before = rule.trigger.get("days_before", 0)

            for event in events_list:
                event_id = f"{event['calendar']}:{event['summary']}:{event['start']}"

                # Check if already triggered
                if is_event_triggered(rule.id, event_id, config):
                    continue

                # Parse event start date with proper timezone handling
                try:
                    event_start_str = event["start"]
                    local_tz = ZoneInfo(config.timezone)

                    if "T" in event_start_str:
                        # Parse datetime with timezone info
                        event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                        # Convert to local timezone for date comparison
                        if event_start.tzinfo:
                            event_start = event_start.astimezone(local_tz)
                        else:
                            event_start = event_start.replace(tzinfo=local_tz)
                    else:
                        # All-day event: parse as date in local timezone
                        event_start = datetime.strptime(event_start_str, "%Y-%m-%d")
                        event_start = event_start.replace(tzinfo=local_tz)

                    # Get current date in local timezone
                    now_local = datetime.now(local_tz)
                except Exception:
                    continue

                # Check if we're in the trigger window (using local timezone dates)
                days_until = (event_start.date() - now_local.date()).days
                if days_until != days_before:
                    continue

                # Use AI to check if event matches rule description
                if matches_event(rule.description, event, config, services):
                    print(f"Firing event rule {rule.id} for {email}: {event['summary']}")
                    execute_action(rule, email, config, services, event=event)
                    mark_event_triggered(rule.id, event_id, config)


def matches_event(
    description: str, event: dict[str, Any], config: Config, services: Services
) -> bool:
    """Use AI to check if an event matches a rule description."""
    prompt = f"""Does this calendar event match the rule description?

RULE DESCRIPTION: "{description}"

EVENT:
- Summary: {event.get('summary', 'No title')}
- Description: {event.get('description', 'None')}
- Calendar: {event.get('calendar', 'Unknown')}

Answer with just "yes" or "no"."""

    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=[prompt],
        )
        return response.text.strip().lower().startswith("yes")
    except Exception as e:
        print(f"AI matching error: {e}")
        return False


def execute_action(
    rule: Rule,
    email: str,
    config: Config,
    services: Services,
    event: dict[str, Any] | None = None,
) -> None:
    """Execute a rule's action."""
    action = rule.action

    if action == "weekly_schedule_summary":
        send_weekly_schedule(email, config, services)
    elif action == "send_reminder":
        send_custom_reminder(rule, email, config, event)
    elif action == "generate_diary":
        generate_diary_for_user(email, config, services)
    else:
        print(f"Unknown action: {action}")


def send_weekly_schedule(email: str, config: Config, services: Services) -> None:
    """Send upcoming week's calendar and weather forecast to user.

    Security: Validates recipient against allowed_senders whitelist.
    """
    # Security: Validate recipient against allowed senders whitelist
    allowed_senders_lower = {s.lower() for s in config.allowed_senders}
    if email.lower() not in allowed_senders_lower:
        print(f"Security: Blocked weekly schedule to non-whitelisted recipient: {email}")
        return

    if not services.calendar_service:
        print("Cannot send weekly schedule: no calendar service")
        return

    try:
        all_events = calendar_client.get_all_upcoming_events(
            services.calendar_service, max_results_per_calendar=20
        )

        # Get weather forecast (use config timezone)
        forecast_data = get_weekly_forecast(timezone=config.timezone)

        # Build plain text version
        weather_text = format_forecast_for_email(forecast_data)
        body = "Here's your schedule for the upcoming week:\n\n"
        body += weather_text + "\n\n"
        body += "=== Your Calendar ===\n\n"
        for cal_name, events in all_events.items():
            if events:
                body += f"--- {cal_name.title()} ---\n"
                for event in events[:10]:
                    body += f"• {event['start']}: {event['summary']}\n"
                body += "\n"
        if not all_events:
            body += "No events scheduled.\n"

        # Build HTML version
        weather_html = format_weather_html(forecast_data.get("forecasts", []))
        calendar_html = format_calendar_html(all_events)
        html_body = html_weekly_schedule(weather_html, calendar_html)

        send_email(
            to_address=email,
            subject="Your Weekly Schedule & Forecast",
            body=body,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            html_body=html_body,
        )
        print(f"Sent weekly schedule with weather to {email}")

    except Exception as e:
        print(f"Error sending weekly schedule: {e}")


def send_custom_reminder(
    rule: Rule, email: str, config: Config, event: dict[str, Any] | None = None
) -> None:
    """Send a custom reminder email.

    Security: Validates recipient against allowed_senders whitelist.
    """
    # Security: Validate recipient against allowed senders whitelist
    allowed_senders_lower = {s.lower() for s in config.allowed_senders}
    if email.lower() not in allowed_senders_lower:
        print(f"Security: Blocked custom reminder to non-whitelisted recipient: {email}")
        return

    template = rule.params.get("message_template", "Reminder: {event_summary}")

    if event:
        # Calculate days until event
        event_start_str = event["start"]
        local_tz = ZoneInfo(config.timezone)
        try:
            if "T" in event_start_str:
                event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                # Convert to local timezone for date comparison
                if event_start.tzinfo:
                    event_start = event_start.astimezone(local_tz)
                else:
                    event_start = event_start.replace(tzinfo=local_tz)
            else:
                # All-day event: parse as date in local timezone
                event_start = datetime.strptime(event_start_str, "%Y-%m-%d")
                event_start = event_start.replace(tzinfo=local_tz)
            now_local = datetime.now(local_tz)
            days = (event_start.date() - now_local.date()).days
        except Exception:
            days = rule.trigger.get("days_before", 0)

        message = template.format(
            event_summary=event.get("summary", "Event"),
            days=days,
            event_start=event.get("start", ""),
        )
    else:
        message = template

    try:
        send_email(
            to_address=email,
            subject=message[:80],
            body=message,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
        )
        print(f"Sent custom reminder to {email}: {message[:50]}...")
    except Exception as e:
        print(f"Error sending custom reminder: {e}")


def check_weekly_diary(config: Config, services: Services) -> None:
    """Check if it's time to generate weekly diaries (Sunday 11pm)."""
    local_tz = ZoneInfo(config.timezone)
    now = datetime.now(local_tz)
    # Only run on Sunday at 11pm
    if now.weekday() != 6 or now.hour != 23:
        return

    # Only run once per hour (check minute)
    if now.minute > 1:
        return

    print("Generating weekly diaries...")

    # Get all known users from identities and user_data
    users = set(IDENTITIES.keys())
    user_data = load_user_data(config)
    users.update(user_data.keys())

    for email in users:
        try:
            generate_diary_for_user(email, config, services)
        except Exception as e:
            print(f"Error generating diary for {email}: {e}")


def check_triggered_cleanup(config: Config) -> None:
    """Clean up old triggered event entries daily at 3am.

    This prevents the triggered events file from growing unboundedly.
    """
    local_tz = ZoneInfo(config.timezone)
    now = datetime.now(local_tz)

    # Only run at 3am
    if now.hour != 3:
        return

    # Only run once per hour (check minute)
    if now.minute > 1:
        return

    removed = cleanup_old_triggered(config, max_age_days=90)
    if removed > 0:
        print(f"Cleaned up {removed} old triggered event entries")


def generate_diary_for_user(email: str, config: Config, services: Services) -> None:
    """Generate a diary entry for a user's past week."""
    week_start, week_end = get_week_bounds(tz=config.timezone)
    week_id = get_week_id(tz=config.timezone)

    # Collect data sources
    sources: dict[str, list[str]] = {
        "todos_completed": [],
        "reminders_fired": [],
        "calendar_events": [],
    }

    # Get completed todos from past week
    local_tz = ZoneInfo(config.timezone)
    todos = get_todos(email, config, include_done=True)
    for todo in todos:
        if todo.get("done") and todo.get("completed_at"):
            completed_at = datetime.fromisoformat(todo["completed_at"])
            # Handle both tz-aware (new) and naive (legacy) timestamps
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=local_tz)
            if week_start <= completed_at <= week_end:
                sources["todos_completed"].append(todo["text"])

    # Get fired reminders
    sources["reminders_fired"] = get_reminders_in_range(email, week_start, week_end, config)

    # Get calendar events from past week using time range query
    if services.calendar_service:
        try:
            all_events = calendar_client.get_all_events_in_range(
                services.calendar_service,
                time_min=week_start,
                time_max=week_end,
                max_results_per_calendar=50,
            )
            for cal_name, events in all_events.items():
                for event in events:
                    sources["calendar_events"].append(event["summary"])
        except Exception as e:
            print(f"Could not fetch calendar for diary: {e}")

    # Generate diary content with AI
    prompt = f"""Generate a brief, friendly weekly diary entry for the user based on their activity.

WEEK: {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}

COMPLETED TODOS:
{chr(10).join('- ' + t for t in sources['todos_completed']) or '- None'}

REMINDERS THAT FIRED:
{chr(10).join('- ' + r for r in sources['reminders_fired']) or '- None'}

CALENDAR EVENTS:
{chr(10).join('- ' + e for e in sources['calendar_events']) or '- None'}

Write a 2-3 paragraph summary of their week. Be warm and personal. Highlight accomplishments and notable events. If there's little activity, keep it brief."""

    try:
        response = services.gemini_client.models.generate_content(
            model=config.gemini_model,
            contents=[prompt],
        )
        content = response.text

        entry = DiaryEntry(
            id=week_id,
            user_email=email,
            week_start=week_start.strftime("%Y-%m-%d"),
            week_end=week_end.strftime("%Y-%m-%d"),
            content=content,
            sources=sources,
        )
        save_diary_entry(entry, config)
        print(f"Generated diary entry {week_id} for {email}")

    except Exception as e:
        print(f"Error generating diary content: {e}")
