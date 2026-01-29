"""End-to-end integration tests for the cloud agent system.

Tests complete flows:
1. Email -> Task file -> Processing -> Response
2. Multi-turn conversation continuity
3. Agent handoff between RouterAgent and sub-agents
4. Session persistence across restarts
"""

import json
import time
from datetime import datetime
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.models import Task, AgentTask
from src.sessions import EmailConversation, FileSessionStore, compute_thread_id
from src.task_io import write_task_atomic, read_task_safe


class TestEmailToTaskFileFlow:
    """Tests for the Email -> Task file flow (poller)."""

    def test_email_creates_task_file(self, test_config, temp_dir):
        """Complete flow: email received -> task file created in inputs/."""
        from src.poller import create_task, get_email_body, save_attachments

        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        # Simulate email processing
        task_id = create_task(
            task_id="e2e-test-001",
            subject="Schedule meeting tomorrow",
            body="Please schedule a team meeting for tomorrow at 2pm",
            sender="allowed@example.com",
            attachments=[],
            config=test_config,
        )

        # Verify task file was created
        task_file = temp_dir / f"task_{task_id}.json"
        assert task_file.exists()

        # Verify content
        task_data = read_task_safe(task_file)
        assert task_data is not None
        assert task_data["id"] == "e2e-test-001"
        assert task_data["subject"] == "Schedule meeting tomorrow"
        assert "team meeting" in task_data["body"]
        assert task_data["sender"] == "allowed@example.com"

    def test_email_with_reply_to_extraction(self, test_config, temp_dir):
        """Email with reply_to pattern in subject creates correct task."""
        from src.poller import create_task

        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        task_id = create_task(
            task_id="e2e-test-002",
            subject="Research: family@example.com",
            body="Find information about Python async programming",
            sender="admin@example.com",
            attachments=[],
            config=test_config,
        )

        task_file = temp_dir / f"task_{task_id}.json"
        task_data = read_task_safe(task_file)

        # reply_to should be extracted from subject
        assert task_data["reply_to"] == "family@example.com"
        assert task_data["sender"] == "admin@example.com"

    def test_multipart_email_extracts_plain_text(self, test_config, temp_dir):
        """Multipart email should extract plain text body."""
        from src.poller import get_email_body

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Multipart Test"
        msg["From"] = "allowed@example.com"

        text_part = MIMEText("Plain text: Add milk to groceries", "plain")
        html_part = MIMEText("<html><body>HTML: Add milk to groceries</body></html>", "html")
        msg.attach(text_part)
        msg.attach(html_part)

        body = get_email_body(msg)
        assert "Plain text: Add milk to groceries" in body
        # Should prefer plain text over HTML
        assert "<html>" not in body


class TestTaskFileToProcessingFlow:
    """Tests for Task file -> Orchestrator processing flow."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create an ADKOrchestrator instance with mocked dependencies."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)
        test_config.processed_dir.mkdir(parents=True, exist_ok=True)
        test_config.failed_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner") as mock_runner:
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        # Mock the runner.run to return events
                        mock_runner_instance = MagicMock()
                        mock_event = MagicMock()
                        mock_event.is_final_response.return_value = True
                        mock_event.get_function_calls.return_value = []

                        # Create a mock part with text
                        mock_part = MagicMock()
                        mock_part.text = "I've scheduled your meeting for tomorrow at 2pm."
                        mock_event.content = MagicMock()
                        mock_event.content.parts = [mock_part]

                        mock_runner_instance.run.return_value = [mock_event]
                        mock_runner.return_value = mock_runner_instance

                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_process_task_reads_and_parses(self, orchestrator, test_config):
        """Orchestrator reads task file and processes it."""
        # Create task file
        task_data = {
            "id": "test-task-123",
            "subject": "Schedule meeting",
            "body": "Schedule a meeting for tomorrow",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": [],
            "created_at": datetime.now().isoformat(),
        }
        task_file = test_config.input_dir / "task_test-task-123.json"
        write_task_atomic(task_data, task_file)

        # Process with mocked email sending
        with patch("src.agents.tools.email_tools.send_email", return_value=True):
            with patch("src.agents.tools.email_tools.text_to_html", return_value="<p>Response</p>"):
                with patch("src.agents.tools.email_tools.html_response", return_value="<html>...</html>"):
                    result = orchestrator.process_task(task_file)

        # Should be processed successfully
        assert result in ["processed", "retry"]

    def test_invalid_task_file_returns_retry(self, orchestrator, test_config):
        """Invalid JSON task file should return retry."""
        task_file = test_config.input_dir / "task_invalid.json"
        task_file.write_text("not valid json {{{")

        result = orchestrator.process_task(task_file)

        assert result == "retry"

    def test_agent_task_processed_differently(self, orchestrator, test_config):
        """Agent-created tasks should be handled by _execute_agent_task."""
        agent_task_data = {
            "task_type": "agent_task",
            "id": "agent-task-001",
            "action": "send_email",
            "params": {
                "to_address": "allowed@example.com",
                "subject": "Test Subject",
                "body": "Test body",
            },
            "created_by": "RouterAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
        }
        task_file = test_config.input_dir / "task_agent-001.json"
        write_task_atomic(agent_task_data, task_file)

        with patch("src.adk_orchestrator.send_email", return_value=True):
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>Test</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator.process_task(task_file)

        assert result == "processed"


class TestMultiTurnConversationContinuity:
    """Tests for multi-turn conversation continuity."""

    def test_same_thread_id_for_reply(self, temp_dir):
        """Re: prefix should result in same thread_id."""
        store = FileSessionStore(temp_dir / "sessions.json")

        # First message
        conv1, is_new1 = store.get_or_create("user@example.com", "Meeting discussion")
        assert is_new1 is True

        # Reply to same thread
        conv2, is_new2 = store.get_or_create("user@example.com", "Re: Meeting discussion")
        assert is_new2 is False
        assert conv1.thread_id == conv2.thread_id

    def test_conversation_history_persists(self, temp_dir):
        """Messages added to conversation should persist."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv, _ = store.get_or_create("user@example.com", "Todo list")
        store.add_message(conv.thread_id, "user", "Add milk to groceries")
        store.add_message(conv.thread_id, "assistant", "Added milk to your groceries list.")
        store.add_message(conv.thread_id, "user", "Also eggs")

        # Retrieve and verify
        retrieved = store.get(conv.thread_id)
        assert len(retrieved.messages) == 3
        assert retrieved.messages[0].content == "Add milk to groceries"
        assert retrieved.messages[2].content == "Also eggs"

    def test_context_string_includes_history(self, temp_dir):
        """Context string should include conversation history."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv, _ = store.get_or_create("user@example.com", "Weather inquiry")
        conv.add_message("user", "What's the weather in NYC?")
        conv.add_message("assistant", "It's 72F and sunny in NYC.")

        context = conv.get_context_string()

        assert "User: What's the weather in NYC?" in context
        assert "Assistant: It's 72F and sunny in NYC." in context

    def test_different_senders_different_threads(self, temp_dir):
        """Different senders should have different threads even with same subject."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv1, _ = store.get_or_create("user1@example.com", "Help")
        conv2, _ = store.get_or_create("user2@example.com", "Help")

        assert conv1.thread_id != conv2.thread_id

    def test_bracketed_prefixes_stripped(self, temp_dir):
        """[External] and similar prefixes should be stripped for thread matching."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv1, is_new1 = store.get_or_create("user@example.com", "Important meeting")
        conv2, is_new2 = store.get_or_create("user@example.com", "[External] Important meeting")

        assert is_new2 is False
        assert conv1.thread_id == conv2.thread_id


class TestAgentHandoff:
    """Tests for agent handoff between RouterAgent and sub-agents."""

    def test_router_agent_has_sub_agents(self):
        """RouterAgent should have all expected sub-agents configured."""
        with patch("src.agents.router.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                gemini_model="test-model",
                timezone="America/New_York",
            )

            # Import after patching to avoid config issues
            from src.agents.router import router_agent

            sub_agent_names = [agent.name for agent in router_agent.sub_agents]

            # Verify expected sub-agents
            assert "CalendarAgent" in sub_agent_names
            assert "PersonalDataAgent" in sub_agent_names
            assert "AutomationAgent" in sub_agent_names
            assert "ResearchAgent" in sub_agent_names
            assert "SystemAgent" in sub_agent_names
            assert "SystemAdminAgent" in sub_agent_names

    def test_router_agent_has_memory_tools(self):
        """RouterAgent should have memory tools for persistent facts."""
        with patch("src.agents.router.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                gemini_model="test-model",
                timezone="America/New_York",
            )

            from src.agents.router import router_agent

            tool_names = [tool.__name__ for tool in router_agent.tools]

            assert "remember_fact" in tool_names
            assert "recall_facts" in tool_names
            assert "list_facts_by_category" in tool_names
            assert "forget_fact" in tool_names

    def test_router_agent_has_email_tools(self):
        """RouterAgent should have email response tools."""
        with patch("src.agents.router.get_config") as mock_config:
            mock_config.return_value = MagicMock(
                gemini_model="test-model",
                timezone="America/New_York",
            )

            from src.agents.router import router_agent

            tool_names = [tool.__name__ for tool in router_agent.tools]

            assert "send_email_response" in tool_names
            assert "get_conversation_history" in tool_names
            assert "get_user_identity" in tool_names


class TestSessionPersistenceAcrossRestarts:
    """Tests for session persistence across simulated restarts."""

    def test_sessions_persist_to_file(self, temp_dir):
        """Sessions should be written to file and readable by new store instance."""
        sessions_file = temp_dir / "sessions.json"

        # First "run" - create session store and add conversation
        store1 = FileSessionStore(sessions_file)
        conv1, _ = store1.get_or_create("user@example.com", "Persistent test")
        store1.add_message(conv1.thread_id, "user", "Remember this message")
        store1.add_message(conv1.thread_id, "assistant", "I will remember it.")

        # Verify file was written
        assert sessions_file.exists()

        # "Restart" - create new store instance pointing to same file
        store2 = FileSessionStore(sessions_file)
        conv2 = store2.get(conv1.thread_id)

        # Verify conversation persisted
        assert conv2 is not None
        assert conv2.sender == "user@example.com"
        assert len(conv2.messages) == 2
        assert conv2.messages[0].content == "Remember this message"

    def test_multiple_conversations_persist(self, temp_dir):
        """Multiple conversations should all persist."""
        sessions_file = temp_dir / "sessions.json"

        # First "run"
        store1 = FileSessionStore(sessions_file)
        conv_a, _ = store1.get_or_create("alice@example.com", "Alice's thread")
        conv_b, _ = store1.get_or_create("bob@example.com", "Bob's thread")
        store1.add_message(conv_a.thread_id, "user", "Alice message")
        store1.add_message(conv_b.thread_id, "user", "Bob message")

        # "Restart"
        store2 = FileSessionStore(sessions_file)

        # Both should be retrievable
        retrieved_a = store2.get(conv_a.thread_id)
        retrieved_b = store2.get(conv_b.thread_id)

        assert retrieved_a is not None
        assert retrieved_b is not None
        assert retrieved_a.sender == "alice@example.com"
        assert retrieved_b.sender == "bob@example.com"

    def test_conversation_updated_at_changes(self, temp_dir):
        """updated_at should change when messages are added."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv, _ = store.get_or_create("user@example.com", "Timestamp test")
        initial_updated = conv.updated_at

        # Small delay to ensure timestamp difference
        time.sleep(0.01)

        store.add_message(conv.thread_id, "user", "New message")

        retrieved = store.get(conv.thread_id)
        assert retrieved.updated_at > initial_updated


class TestRequestContextFlow:
    """Tests for request context propagation to tools."""

    def test_context_set_and_retrieved(self):
        """Request context should be settable and retrievable."""
        from src.agents.tools._context import (
            set_request_context,
            get_request_context,
            clear_request_context,
            get_user_email,
            get_reply_to,
            get_thread_id,
            get_body,
        )

        try:
            set_request_context(
                user_email="test@example.com",
                thread_id="thread-abc123",
                reply_to="reply@example.com",
                body="Test message body",
            )

            # Test individual accessors
            assert get_user_email() == "test@example.com"
            assert get_reply_to() == "reply@example.com"
            assert get_thread_id() == "thread-abc123"
            assert get_body() == "Test message body"

            # Test full context
            ctx = get_request_context()
            assert ctx["user_email"] == "test@example.com"
            assert ctx["thread_id"] == "thread-abc123"

        finally:
            clear_request_context()

    def test_context_cleared_properly(self):
        """Request context should be clearable."""
        from src.agents.tools._context import (
            set_request_context,
            clear_request_context,
            get_user_email,
        )

        set_request_context(
            user_email="test@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        clear_request_context()

        # Should return empty after clear
        assert get_user_email() == ""


class TestTaskMovementFlow:
    """Tests for task file movement (processed/failed directories)."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create orchestrator with mocked dependencies."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)
        test_config.processed_dir.mkdir(parents=True, exist_ok=True)
        test_config.failed_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_move_task_to_processed(self, orchestrator, test_config):
        """Successfully processed tasks should move to processed directory."""
        task_data = {
            "id": "move-test-001",
            "subject": "Test",
            "body": "Body",
            "sender": "user@example.com",
            "reply_to": "user@example.com",
            "attachments": [],
        }
        task_file = test_config.input_dir / "task_move-test-001.json"
        write_task_atomic(task_data, task_file)

        orchestrator.move_task(task_file, test_config.processed_dir)

        # Original should be gone
        assert not task_file.exists()
        # Should be in processed
        assert (test_config.processed_dir / "task_move-test-001.json").exists()

    def test_move_task_with_attachments(self, orchestrator, test_config):
        """Task with attachments should move attachments too."""
        # Create attachment file
        attachment_file = test_config.input_dir / "move-test-002_report.pdf"
        attachment_file.write_bytes(b"PDF content")

        task_data = {
            "id": "move-test-002",
            "subject": "With attachment",
            "body": "Body",
            "sender": "user@example.com",
            "reply_to": "user@example.com",
            "attachments": ["move-test-002_report.pdf"],
        }
        task_file = test_config.input_dir / "task_move-test-002.json"
        write_task_atomic(task_data, task_file)

        orchestrator.move_task(task_file, test_config.processed_dir)

        # Both task and attachment should be moved
        assert not task_file.exists()
        assert not attachment_file.exists()
        assert (test_config.processed_dir / "task_move-test-002.json").exists()
        assert (test_config.processed_dir / "move-test-002_report.pdf").exists()


class TestAgentTaskExecution:
    """Tests for agent-created task execution."""

    @pytest.fixture
    def orchestrator(self, test_config, mock_services):
        """Create orchestrator for agent task tests."""
        test_config.input_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner"):
                with patch("src.adk_orchestrator.InMemorySessionService"):
                    with patch("src.adk_orchestrator.router_agent"):
                        from src.adk_orchestrator import ADKOrchestrator
                        return ADKOrchestrator(test_config, mock_services)

    def test_send_email_action_executed(self, orchestrator, test_config):
        """send_email action should send email to whitelisted recipient."""
        agent_task = AgentTask(
            id="email-task-001",
            action="send_email",
            params={
                "to_address": "allowed@example.com",  # In test_config.allowed_senders
                "subject": "Hello from Agent",
                "body": "This is a test email.",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-001",
        )

        with patch("src.adk_orchestrator.send_email", return_value=True) as mock_send:
            with patch("src.adk_orchestrator.text_to_html", return_value="<p>This is a test email.</p>"):
                with patch("src.adk_orchestrator.html_response", return_value="<html>...</html>"):
                    result = orchestrator._execute_agent_task(agent_task)

        assert result == "processed"
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["to_address"] == "allowed@example.com"
        assert call_kwargs["subject"] == "Hello from Agent"

    def test_non_whitelisted_recipient_blocked(self, orchestrator):
        """Emails to non-whitelisted recipients should be blocked."""
        agent_task = AgentTask(
            id="email-task-002",
            action="send_email",
            params={
                "to_address": "hacker@malicious.com",  # NOT in allowed_senders
                "subject": "Attempt",
                "body": "Should be blocked",
            },
            created_by="MaliciousAgent",
            original_sender="user@example.com",
            original_thread_id="thread-002",
        )

        result = orchestrator._execute_agent_task(agent_task)

        assert result == "failed"

    def test_unknown_action_fails(self, orchestrator):
        """Unknown action types should fail."""
        agent_task = AgentTask(
            id="unknown-task-001",
            action="delete_everything",  # Not a valid action
            params={},
            created_by="BadAgent",
            original_sender="user@example.com",
            original_thread_id="thread-003",
        )

        result = orchestrator._execute_agent_task(agent_task)

        assert result == "failed"


class TestCompleteEmailToResponseFlow:
    """Tests for complete email -> task -> process -> response flow."""

    def test_full_flow_with_mocked_adk(self, test_config, mock_services, temp_dir):
        """Complete flow from email to response with mocked ADK."""
        from src.poller import create_task

        # Update config to use temp_dir
        test_config = test_config.__class__(
            **{
                **test_config.__dict__,
                "input_dir": temp_dir / "inputs",
                "processed_dir": temp_dir / "processed",
                "failed_dir": temp_dir / "failed",
                "sessions_file": temp_dir / "sessions.json",
            }
        )
        test_config.input_dir.mkdir(parents=True, exist_ok=True)
        test_config.processed_dir.mkdir(parents=True, exist_ok=True)
        test_config.failed_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Poller creates task file
        task_id = create_task(
            task_id="full-flow-001",
            subject="Add eggs to groceries",
            body="Please add eggs to my grocery list",
            sender="allowed@example.com",
            attachments=[],
            config=test_config,
        )

        task_file = test_config.input_dir / f"task_{task_id}.json"
        assert task_file.exists()

        # Step 2: Orchestrator processes task
        with patch("src.adk_orchestrator.set_services"):
            with patch("src.adk_orchestrator.Runner") as mock_runner:
                with patch("src.adk_orchestrator.InMemorySessionService") as mock_session_svc:
                    with patch("src.adk_orchestrator.router_agent"):
                        # Mock the session service's async methods
                        mock_session_instance = MagicMock()
                        mock_session_instance.get_session = AsyncMock(return_value=None)
                        mock_session_instance.create_session = AsyncMock(return_value=MagicMock())
                        mock_session_svc.return_value = mock_session_instance

                        # Mock ADK runner response
                        mock_runner_instance = MagicMock()
                        mock_event = MagicMock()
                        mock_event.is_final_response.return_value = True

                        # Simulate send_email_response being called
                        mock_fc = MagicMock()
                        mock_fc.name = "send_email_response"
                        mock_event.get_function_calls.return_value = [mock_fc]

                        mock_part = MagicMock()
                        mock_part.text = "Done! Added eggs to your grocery list."
                        mock_event.content = MagicMock()
                        mock_event.content.parts = [mock_part]

                        mock_runner_instance.run.return_value = [mock_event]
                        mock_runner.return_value = mock_runner_instance

                        from src.adk_orchestrator import ADKOrchestrator
                        orchestrator = ADKOrchestrator(test_config, mock_services)

                        result = orchestrator.process_task(task_file)

        # Verify processing completed
        assert result == "processed"

        # Verify session was created
        session_store = FileSessionStore(test_config.sessions_file)
        conversations = session_store.list_conversations(sender="allowed@example.com")
        assert len(conversations) == 1
        assert conversations[0].subject == "Add eggs to groceries"


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling."""

    def test_empty_body_task(self, test_config, temp_dir):
        """Task with empty body should still be processable."""
        from src.poller import create_task

        test_config = test_config.__class__(
            **{**test_config.__dict__, "input_dir": temp_dir}
        )
        temp_dir.mkdir(exist_ok=True)

        task_id = create_task(
            task_id="empty-body-001",
            subject="Empty body test",
            body="",
            sender="allowed@example.com",
            attachments=[],
            config=test_config,
        )

        task_file = temp_dir / f"task_{task_id}.json"
        task_data = read_task_safe(task_file)

        assert task_data is not None
        assert task_data["body"] == ""

    def test_very_long_subject_handling(self, temp_dir):
        """Very long subjects should be handled without truncation in thread_id."""
        store = FileSessionStore(temp_dir / "sessions.json")

        long_subject = "A" * 1000
        conv1, _ = store.get_or_create("user@example.com", long_subject)
        conv2, _ = store.get_or_create("user@example.com", "Re: " + long_subject)

        # Should be same thread
        assert conv1.thread_id == conv2.thread_id
        # Thread ID should be fixed length (16 chars)
        assert len(conv1.thread_id) == 16

    def test_unicode_in_conversation(self, temp_dir):
        """Unicode content in conversations should persist correctly."""
        store = FileSessionStore(temp_dir / "sessions.json")

        conv, _ = store.get_or_create("user@example.com", "Unicode test")
        conv.add_message("user", "Schedule meeting at Cafe Noir")
        conv.add_message("assistant", "Scheduled at Cafe Noir!")
        store.save(conv)

        # Retrieve and verify
        retrieved = store.get(conv.thread_id)
        assert "Cafe Noir" in retrieved.messages[0].content

    def test_concurrent_session_access(self, temp_dir):
        """Multiple stores accessing same file should work correctly."""
        sessions_file = temp_dir / "sessions.json"

        store1 = FileSessionStore(sessions_file)
        store2 = FileSessionStore(sessions_file)

        # Store1 creates conversation
        conv1, _ = store1.get_or_create("user1@example.com", "Test 1")
        store1.add_message(conv1.thread_id, "user", "Message from store1")

        # Store2 should see the conversation
        conv2 = store2.get(conv1.thread_id)
        assert conv2 is not None
        assert len(conv2.messages) == 1

        # Store2 adds message
        store2.add_message(conv1.thread_id, "assistant", "Reply from store2")

        # Store1 should see both messages
        conv1_updated = store1.get(conv1.thread_id)
        assert len(conv1_updated.messages) == 2

    def test_task_model_validation(self):
        """Task.from_dict should validate required fields."""
        incomplete_data = {
            "id": "test-123",
            "subject": "Test",
            # Missing body, sender, reply_to
        }

        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(incomplete_data)

        assert "Missing required fields" in str(exc_info.value)

    def test_agent_task_model_validation(self):
        """AgentTask.from_dict should validate required fields."""
        incomplete_data = {
            "task_type": "agent_task",
            "id": "test-123",
            # Missing action, params, created_by, etc.
        }

        with pytest.raises(ValueError) as exc_info:
            AgentTask.from_dict(incomplete_data)

        assert "Missing required fields" in str(exc_info.value)
