"""ADK-powered orchestrator using multi-agent architecture.

Replaces the handler-based orchestrator with Google ADK agents.
"""

import asyncio
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted
from google.genai.errors import ServerError

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents import router_agent
from src.agents.tools._context import (
    clear_request_context,
    set_request_context,
    set_services,
)
from src.clients.email import html_response, send_email, text_to_html
from src.config import Config, get_config
from src.reminders import load_existing_reminders
from src.models import AgentTask, Task
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

    def _execute_agent_task(self, agent_task: AgentTask) -> str:
        """Execute an agent-created task directly.

        Args:
            agent_task: The agent task to execute.

        Returns:
            "processed" - task executed successfully
            "failed" - task execution failed
        """
        print(f"  Agent task: {agent_task.action} (created by {agent_task.created_by})")

        if agent_task.action == "send_email":
            return self._execute_send_email(agent_task)
        else:
            print(f"  Unknown action: {agent_task.action}")
            return "failed"

    def _execute_send_email(self, agent_task: AgentTask) -> str:
        """Execute a send_email agent task.

        Args:
            agent_task: The agent task with send_email action.

        Returns:
            "processed" or "failed"
        """
        params = agent_task.params
        to_address = params.get("to_address")
        subject = params.get("subject")
        body = params.get("body")
        icon = params.get("icon", "💬")  # Default: speech balloon

        if not all([to_address, subject, body]):
            missing = [p for p in ("to_address", "subject", "body") if not params.get(p)]
            print(f"  Missing required params for send_email: {missing}")
            return "failed"

        # Defense in depth: validate recipient even though tool already checked
        if to_address not in self.config.allowed_senders:
            print(f"  Security: Blocked email to non-whitelisted recipient: {to_address}")
            return "failed"

        try:
            # Generate HTML version
            html_content = text_to_html(body)
            html_body = html_response(html_content, title=subject, icon=icon)

            success = send_email(
                to_address=to_address,
                subject=subject,
                body=body,
                email_user=self.config.email_user,
                email_pass=self.config.email_pass,
                smtp_server=self.config.smtp_server,
                smtp_port=self.config.smtp_port,
                html_body=html_body,
            )

            if success:
                print(f"  Email sent to {to_address}")
                return "processed"
            else:
                print(f"  Failed to send email to {to_address}")
                return "failed"

        except Exception as e:
            print(f"  Email error: {e}")
            return "failed"

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
        tz = ZoneInfo(self.config.timezone)
        now = datetime.now(tz)
        lines = [
            f"From: {task.sender}",
            f"Subject: {task.subject}",
            f"Date: {now.strftime('%Y-%m-%d %H:%M')} ({self.config.timezone})",
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

            # Check if this is an agent-created task
            if AgentTask.is_agent_task(task_data):
                try:
                    agent_task = AgentTask.from_dict(task_data)
                    return self._execute_agent_task(agent_task)
                except ValueError as e:
                    print(f"  Invalid agent task: {e}")
                    return "failed"

            # Regular email-originated task
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

            # Ensure ADK session exists (async methods need asyncio.run)
            async def ensure_session():
                session = await self.session_service.get_session(
                    app_name="cloud_agent",
                    user_id=task.sender,
                    session_id=session_id,
                )
                if session is None:
                    await self.session_service.create_session(
                        app_name="cloud_agent",
                        user_id=task.sender,
                        session_id=session_id,
                    )

            asyncio.run(ensure_session())

            print(f"  Thread: {conversation.thread_id} ({'new' if is_new else 'continuing'})")

            # Build message content for ADK with text and any image attachments
            parts = [types.Part(text=context)]

            # Add image attachments
            for attachment in task.attachments:
                attachment_path = self.config.input_dir / attachment
                if attachment_path.exists():
                    suffix = attachment_path.suffix.lower()
                    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                        try:
                            image_data = attachment_path.read_bytes()
                            mime_type = {
                                ".png": "image/png",
                                ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg",
                                ".gif": "image/gif",
                                ".webp": "image/webp",
                            }.get(suffix, "image/png")
                            parts.append(types.Part.from_bytes(
                                data=image_data,
                                mime_type=mime_type,
                            ))
                            print(f"  Attached image: {attachment}")
                        except Exception as e:
                            print(f"  Failed to attach {attachment}: {e}")

            user_message = types.Content(
                parts=parts,
                role="user",
            )

            # Run with retry for transient API errors (503, rate limits)
            response_text = ""
            email_sent = False
            max_retries = 3
            base_delay = 5  # seconds

            for attempt in range(max_retries):
                try:
                    response_text = ""
                    email_sent = False
                    for event in self.runner.run(
                        user_id=task.sender,
                        session_id=session_id,
                        new_message=user_message,
                    ):
                        # Track if email was sent via tool call
                        try:
                            func_calls = event.get_function_calls()
                            if func_calls:
                                for fc in func_calls:
                                    if hasattr(fc, "name") and fc.name == "send_email_response":
                                        email_sent = True
                        except (AttributeError, TypeError):
                            pass  # Event doesn't support function calls
                        # Collect final response
                        if event.is_final_response() and event.content:
                            for part in event.content.parts:
                                if hasattr(part, "text"):
                                    response_text += part.text
                    break  # Success, exit retry loop

                except (ServiceUnavailable, ResourceExhausted, ServerError) as e:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    if attempt < max_retries - 1:
                        print(f"  API error (attempt {attempt + 1}/{max_retries}): {e}")
                        print(f"  Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        print(f"  API error after {max_retries} attempts: {e}")
                        raise  # Re-raise on final attempt

            # Fallback: if agent returned text but didn't send email, send it now
            if response_text and not email_sent:
                print(f"  Warning: Agent did not send email, using fallback")
                from src.agents.tools.email_tools import send_email_response
                send_email_response(
                    subject=f"Re: {task.subject}",
                    body=response_text,
                )

            # Record assistant response
            if response_text:
                self.session_store.add_message(
                    conversation.thread_id,
                    "assistant",
                    response_text,
                )

            # Only mark as processed if we actually did something
            # (ADK async errors don't propagate to main thread)
            if email_sent or response_text:
                print(f"  Completed processing for {task.sender}")
                return "processed"
            else:
                print(f"  No response generated for {task.sender}, will retry")
                return "retry"

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
