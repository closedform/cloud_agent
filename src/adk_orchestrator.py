"""ADK-powered orchestrator using multi-agent architecture.

Replaces the handler-based orchestrator with Google ADK agents.
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents import router_agent
from src.agents.tools._context import (
    clear_request_context,
    set_request_context,
    set_services,
)
from src.config import Config, get_config
from src.reminders import load_existing_reminders
from src.models import Task
from src.scheduler import run_scheduler
from src.services import Services, create_services
from src.sessions import EmailConversation, FileSessionStore, compute_thread_id
from src.task_io import read_task_safe


class ADKOrchestrator:
    """Orchestrator using ADK agents for task processing."""

    def __init__(self, config: Config, services: Services):
        """Initialize the ADK orchestrator.

        Args:
            config: Application configuration.
            services: Initialized external services.
        """
        self.config = config
        self.services = services
        self.session_store = FileSessionStore(config.sessions_file)

        # Set global services for tools
        set_services(services)

        # Create ADK runner with session service
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=router_agent,
            app_name="cloud_agent",
            session_service=self.session_service,
        )

    def _build_context(
        self,
        task: Task,
        conversation: EmailConversation,
        is_new: bool,
    ) -> str:
        """Build context string for the agent.

        Args:
            task: The incoming task.
            conversation: The conversation object.
            is_new: Whether this is a new conversation.

        Returns:
            Context string for the agent.
        """
        lines = [
            f"From: {task.sender}",
            f"Subject: {task.subject}",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # Add conversation history for multi-turn
        if not is_new and conversation.messages:
            lines.append("=== Previous Conversation ===")
            history = conversation.get_context_string(max_messages=5)
            lines.append(history)
            lines.append("")
            lines.append("=== New Message ===")

        lines.append(task.body)

        return "\n".join(lines)

    def process_task(self, task_file: Path) -> str:
        """Process a single task file.

        Args:
            task_file: Path to the task JSON file.

        Returns:
            "processed" - task handled, move to processed/
            "retry" - task couldn't be parsed, leave for retry
            "failed" - task exceeded max retries, move to failed/
        """
        print(f"Processing: {task_file.name}")

        try:
            task_data = read_task_safe(task_file)
            if task_data is None:
                print(f"  Skipping {task_file.name}: could not parse")
                return "retry"

            task = Task.from_dict(task_data)

            # Get or create conversation for multi-turn support
            conversation, is_new = self.session_store.get_or_create(
                sender=task.sender,
                subject=task.subject,
            )

            # Set request context for tools
            set_request_context(
                user_email=task.sender,
                thread_id=conversation.thread_id,
                reply_to=task.reply_to,
                body=task.body,
            )

            # Build context for agent BEFORE adding message to avoid duplication
            # (_build_context includes conversation history and the new message separately)
            context = self._build_context(task, conversation, is_new)

            # Add user message to conversation history AFTER building context
            self.session_store.add_message(
                conversation.thread_id,
                "user",
                task.body,
            )

            # Use thread_id as session_id for ADK
            session_id = conversation.thread_id

            # Run agent (Runner handles session creation internally)
            print(f"  Thread: {conversation.thread_id} ({'new' if is_new else 'continuing'})")

            # Build message content for ADK
            user_message = types.Content(
                parts=[types.Part(text=context)],
                role="user",
            )

            response_text = ""
            for event in self.runner.run(
                user_id=task.sender,
                session_id=session_id,
                new_message=user_message,
            ):
                # Collect final response
                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text"):
                            response_text += part.text

            # Record assistant response
            if response_text:
                self.session_store.add_message(
                    conversation.thread_id,
                    "assistant",
                    response_text,
                )

            print(f"  Completed processing for {task.sender}")
            return "processed"

        except Exception as e:
            print(f"  Error processing task: {e}")
            import traceback
            traceback.print_exc()
            return "retry"  # Allow retry for transient errors

        finally:
            clear_request_context()

    def move_task(self, task_file: Path, dest_dir: Path) -> None:
        """Move task file and attachments to destination folder."""
        try:
            dest_dir.mkdir(exist_ok=True)

            task_data = read_task_safe(task_file)
            if task_data:
                # Move attachments
                for attachment in task_data.get("attachments", []):
                    src = self.config.input_dir / attachment
                    if src.exists():
                        shutil.move(str(src), str(dest_dir / attachment))

            # Move task file
            shutil.move(str(task_file), str(dest_dir / task_file.name))

        except Exception as e:
            print(f"  Move error: {e}")

    def run(self) -> None:
        """Main orchestrator loop."""
        print(f"ADK Orchestrator started. Watching {self.config.input_dir.absolute()}...")

        self.config.input_dir.mkdir(exist_ok=True)
        self.config.processed_dir.mkdir(exist_ok=True)
        self.config.failed_dir.mkdir(exist_ok=True)

        # Load existing reminders
        load_existing_reminders(self.config)

        # Start scheduler in background
        scheduler_thread = threading.Thread(
            target=run_scheduler,
            args=(self.config, self.services),
            daemon=True,
        )
        scheduler_thread.start()

        # Track retry counts
        task_retries: dict[str, int] = {}

        while True:
            # Find task files
            task_files = sorted(self.config.input_dir.glob("task_*.json"))

            for task_file in task_files:
                task_key = task_file.name
                result = self.process_task(task_file)

                if result == "processed":
                    self.move_task(task_file, self.config.processed_dir)
                    task_retries.pop(task_key, None)
                elif result == "retry":
                    task_retries[task_key] = task_retries.get(task_key, 0) + 1
                    if task_retries[task_key] >= self.config.max_task_retries:
                        print(f"  Failed {task_key}: max retries exceeded")
                        self.move_task(task_file, self.config.failed_dir)
                        task_retries.pop(task_key, None)
                elif result == "failed":
                    self.move_task(task_file, self.config.failed_dir)
                    task_retries.pop(task_key, None)

            time.sleep(5)


def main() -> None:
    """Main entry point for the ADK orchestrator."""
    config = get_config()
    services = create_services(config)

    orchestrator = ADKOrchestrator(config, services)
    orchestrator.run()


if __name__ == "__main__":
    main()
