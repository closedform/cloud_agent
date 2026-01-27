"""Orchestrator - the brain of the agent.

Watches the inputs/ folder for task files and routes them to appropriate handlers.
Supports: scheduling, research, calendar queries, reminders, status, help.
"""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from google.genai import types

from src.config import Config, get_config
from src.handlers import get_handler
from src.handlers.reminder import load_existing_reminders
from src.models import Task
from src.services import Services, create_services
from src.task_io import read_task_safe


def classify_intent(task: Task, config: Config, services: Services) -> dict:
    """Use Gemini to classify the intent of an incoming task."""
    subject = task.subject
    body = task.body

    prompt = f"""Classify this email request. Return JSON with intent and any extracted data.

SUBJECT: {subject}
BODY: {body}

CURRENT DATE/TIME: {datetime.now().strftime("%Y-%m-%d %H:%M")} (timezone: {config.timezone})
Use this to resolve relative times like "tomorrow", "next friday".

AVAILABLE INTENTS:
- "schedule": Create a calendar event (keywords: schedule, appointment, meeting, event)
- "research": Research a topic using web search (user wants information/research)
- "calendar_query": Question about existing calendar/schedule (what do I have, when is, am I free)
- "reminder": Set a reminder for later (remind me, don't forget, alert me)
- "status": Check system status (status, health, working)
- "help": Question about how to use this system (how do I, what can you, help)
- "unknown": Can't determine intent

Return JSON:
{{
  "intent": "one of the above",
  "summary": "brief description of what user wants",
  "reminder_time": "ISO datetime (YYYY-MM-DDTHH:MM:SS) if reminder, else null",
  "reminder_message": "reminder text if reminder, else null"
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

        return json.loads(response_text)

    except Exception as e:
        print(f"  Classification error: {e}")
        return {"intent": "unknown", "summary": str(e)}


# Track retry attempts for unparseable tasks
_task_retries: dict[str, int] = {}


def process_task(
    task_file: Path, config: Config, services: Services
) -> str:
    """Process a single task file.

    Returns:
        "processed" - task handled, move to processed/
        "retry" - task couldn't be parsed, leave for retry
        "failed" - task exceeded max retries, move to failed/
    """
    print(f"Processing: {task_file.name}")
    task_key = task_file.name

    try:
        task_data = read_task_safe(task_file)
        if task_data is None:
            # Track retry attempts
            _task_retries[task_key] = _task_retries.get(task_key, 0) + 1
            retries = _task_retries[task_key]

            if retries >= config.max_task_retries:
                print(f"  Failed {task_file.name}: could not parse after {retries} attempts")
                del _task_retries[task_key]
                return "failed"

            print(f"  Skipping {task_file.name}: could not parse (attempt {retries}/{config.max_task_retries})")
            return "retry"

        # Successfully parsed, clear retry counter
        if task_key in _task_retries:
            del _task_retries[task_key]

        task = Task.from_dict(task_data)

        # Classify intent using Gemini
        classification = classify_intent(task, config, services)
        intent = classification.get("intent", "unknown")
        print(f"  Intent: {intent} ({classification.get('summary', '')[:50]})")

        # Update task with classification data
        task.intent = intent
        task.classification = classification

        # Get and run the handler
        handler = get_handler(intent)
        if handler:
            handler(task, config, services)
        else:
            print(f"  Unknown intent '{intent}', skipping")

        return "processed"

    except Exception as e:
        print(f"  Error processing task: {e}")
        return "processed"  # Move to processed to avoid infinite retry on bad data


def move_task(task_file: Path, dest_dir: Path, config: Config) -> None:
    """Move task file and attachments to destination folder."""
    try:
        dest_dir.mkdir(exist_ok=True)

        task_data = read_task_safe(task_file)
        if task_data:
            # Move attachments
            for attachment in task_data.get("attachments", []):
                src = config.input_dir / attachment
                if src.exists():
                    shutil.move(str(src), str(dest_dir / attachment))

        # Move task file
        shutil.move(str(task_file), str(dest_dir / task_file.name))

    except Exception as e:
        print(f"  Move error: {e}")


def main() -> None:
    """Main entry point for the orchestrator."""
    # Initialize configuration and services
    config = get_config()
    services = create_services(config)

    print(f"Orchestrator started. Watching {config.input_dir.absolute()}...")

    config.input_dir.mkdir(exist_ok=True)
    config.processed_dir.mkdir(exist_ok=True)
    config.failed_dir.mkdir(exist_ok=True)

    # Load and schedule any existing reminders
    load_existing_reminders(config)

    while True:
        # Find task files
        task_files = sorted(config.input_dir.glob("task_*.json"))

        for task_file in task_files:
            result = process_task(task_file, config, services)
            if result == "processed":
                move_task(task_file, config.processed_dir, config)
            elif result == "failed":
                move_task(task_file, config.failed_dir, config)
            # "retry" -> leave in place for next iteration

        time.sleep(5)


if __name__ == "__main__":
    main()
