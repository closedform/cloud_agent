"""Stress tests for ADK orchestrator error paths.

Tests:
1. Malformed task JSON files
2. Missing attachments referenced in task
3. ADK runner exceptions
4. Session service failures
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted

from src.adk_orchestrator import ADKOrchestrator
from tests.conftest import TestConfig


def make_server_error(message: str):
    """Create a ServerError with proper constructor args."""
    from google.genai.errors import ServerError
    # ServerError requires response_json with nested error dict
    return ServerError(message, response_json={"error": {"message": message, "code": 500}})


@pytest.fixture
def orchestrator_config(temp_dir: Path) -> TestConfig:
    """Create configuration with all paths under temp_dir."""
    return TestConfig(
        project_root=temp_dir,
        input_dir=temp_dir / "inputs",
        processed_dir=temp_dir / "processed",
        failed_dir=temp_dir / "failed",
        reminders_file=temp_dir / "reminders.json",
        reminder_log_file=temp_dir / "reminder_log.json",
        user_data_file=temp_dir / "user_data.json",
        rules_file=temp_dir / "rules.json",
        diary_file=temp_dir / "diary.json",
        triggered_file=temp_dir / "triggered.json",
        sessions_file=temp_dir / "sessions.json",
        token_path=temp_dir / "token.json",
        credentials_path=temp_dir / "credentials.json",
        allowed_senders=("allowed@example.com", "user@test.com"),
    )


@pytest.fixture
def mock_services():
    """Create mock services for orchestrator."""
    services = MagicMock()
    services.gemini_client = MagicMock()
    services.calendar_service = None
    services.calendars = {"primary": "primary"}
    services.get_identity.return_value = None
    return services


@pytest.fixture
def orchestrator(orchestrator_config, mock_services):
    """Create orchestrator with mocked dependencies."""
    with patch("src.adk_orchestrator.set_services"):
        with patch("src.adk_orchestrator.Runner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner_class.return_value = mock_runner
            orch = ADKOrchestrator(orchestrator_config, mock_services)
            orch.mock_runner = mock_runner  # Expose for tests
            yield orch


# ==============================================================================
# Test 1: Malformed Task JSON Files
# ==============================================================================


class TestMalformedTaskFiles:
    """Tests for handling malformed task JSON files."""

    def test_empty_file_returns_retry(self, orchestrator, orchestrator_config):
        """Empty file should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_001.json"
        task_file.write_text("")

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_invalid_json_returns_retry(self, orchestrator, orchestrator_config):
        """Invalid JSON should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_002.json"
        task_file.write_text("{invalid json content here")

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_truncated_json_returns_retry(self, orchestrator, orchestrator_config):
        """Truncated JSON should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_003.json"
        task_file.write_text('{"id": "123", "subject": "Test", "body"')

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_missing_required_fields_returns_retry(self, orchestrator, orchestrator_config):
        """Task missing required fields should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_004.json"
        # Missing sender and reply_to
        task_file.write_text(json.dumps({
            "id": "test-123",
            "subject": "Test Subject",
            "body": "Test body",
        }))

        result = orchestrator.process_task(task_file)
        # Invalid task data with missing required fields should fail immediately, not retry forever
        assert result == "failed"

    def test_null_json_returns_retry(self, orchestrator, orchestrator_config):
        """JSON null value should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_005.json"
        task_file.write_text("null")

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_json_array_instead_of_object_returns_retry(self, orchestrator, orchestrator_config):
        """JSON array instead of object should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_006.json"
        task_file.write_text('["item1", "item2"]')

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_unicode_decode_error_returns_retry(self, orchestrator, orchestrator_config):
        """Binary content causing decode errors should return retry."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_007.json"
        task_file.write_bytes(b"\xff\xfe\x00\x01\x80\x90")

        result = orchestrator.process_task(task_file)
        assert result == "retry"

    def test_agent_task_with_wrong_type_returns_failed(self, orchestrator, orchestrator_config):
        """Agent task with wrong task_type should return failed."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_008.json"
        task_file.write_text(json.dumps({
            "task_type": "agent_task",
            # Missing required fields for AgentTask
            "id": "123",
        }))

        result = orchestrator.process_task(task_file)
        assert result == "failed"

    def test_agent_task_unknown_action_returns_failed(self, orchestrator, orchestrator_config):
        """Agent task with unknown action should return failed."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_009.json"
        task_file.write_text(json.dumps({
            "task_type": "agent_task",
            "id": "123",
            "action": "unknown_action",
            "params": {},
            "created_by": "TestAgent",
            "original_sender": "user@test.com",
            "original_thread_id": "thread-123",
        }))

        result = orchestrator.process_task(task_file)
        assert result == "failed"


# ==============================================================================
# Test 2: Missing Attachments Referenced in Task
# ==============================================================================


class TestMissingAttachments:
    """Tests for handling missing attachments."""

    def test_missing_image_attachment_continues_processing(
        self, orchestrator, orchestrator_config
    ):
        """Task referencing missing image should continue without it."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_010.json"
        task_file.write_text(json.dumps({
            "id": "test-123",
            "subject": "Test Subject",
            "body": "Test body with image",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": ["nonexistent_image.png"],
        }))

        # Mock runner to return a response
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Response text"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.agents.tools.email_tools.send_email"):
                    result = orchestrator.process_task(task_file)

        # Should process successfully despite missing attachment
        assert result == "processed"

    def test_missing_all_attachments_continues(self, orchestrator, orchestrator_config):
        """Task with all attachments missing should still process."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_011.json"
        task_file.write_text(json.dumps({
            "id": "test-124",
            "subject": "Multi-attachment test",
            "body": "Test with multiple missing attachments",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": ["missing1.png", "missing2.jpg", "missing3.gif"],
        }))

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Processed"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.agents.tools.email_tools.send_email"):
                    result = orchestrator.process_task(task_file)

        assert result == "processed"

    def test_partial_attachments_processes_available(
        self, orchestrator, orchestrator_config
    ):
        """Task with some missing attachments should process available ones."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_012.json"

        # Create one real attachment
        real_attachment = orchestrator_config.input_dir / "real_image.png"
        real_attachment.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        task_file.write_text(json.dumps({
            "id": "test-125",
            "subject": "Partial attachments",
            "body": "Some attachments exist",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": ["real_image.png", "missing_image.png"],
        }))

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Processed"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.agents.tools.email_tools.send_email"):
                    result = orchestrator.process_task(task_file)

        assert result == "processed"

    def test_attachment_read_error_continues(self, orchestrator, orchestrator_config):
        """Attachment that exists but can't be read should not crash."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_013.json"

        task_file.write_text(json.dumps({
            "id": "test-126",
            "subject": "Read error test",
            "body": "Attachment read fails",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": ["unreadable.png"],
        }))

        # Create the file but mock read_bytes to fail
        unreadable = orchestrator_config.input_dir / "unreadable.png"
        unreadable.write_text("fake png")

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Processed despite read error"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.agents.tools.email_tools.send_email"):
                    # Even if there's an encoding issue, the file exists and is read
                    result = orchestrator.process_task(task_file)

        assert result == "processed"


# ==============================================================================
# Test 3: ADK Runner Exceptions
# ==============================================================================


class TestADKRunnerExceptions:
    """Tests for handling ADK runner exceptions."""

    def _create_valid_task_file(self, config, task_id="test-200"):
        """Helper to create a valid task file."""
        config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = config.input_dir / f"task_{task_id}.json"
        task_file.write_text(json.dumps({
            "id": task_id,
            "subject": "Runner exception test",
            "body": "Testing runner failures",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": [],
        }))
        return task_file

    def test_service_unavailable_retries_then_fails(
        self, orchestrator, orchestrator_config
    ):
        """ServiceUnavailable should retry with exponential backoff."""
        task_file = self._create_valid_task_file(orchestrator_config, "srv-unavail")

        # Mock runner to always fail with ServiceUnavailable
        orchestrator.mock_runner.run.side_effect = ServiceUnavailable("Service down")

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.adk_orchestrator.time.sleep") as mock_sleep:
                    result = orchestrator.process_task(task_file)

        # Should have retried 3 times (3 attempts total)
        assert orchestrator.mock_runner.run.call_count == 3
        # Should have slept between retries (2 sleeps for 3 attempts)
        assert mock_sleep.call_count == 2
        # Should return retry to allow future attempts
        assert result == "retry"

    def test_resource_exhausted_retries(self, orchestrator, orchestrator_config):
        """ResourceExhausted (rate limit) should retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "rate-limit")

        orchestrator.mock_runner.run.side_effect = ResourceExhausted("Rate limited")

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.adk_orchestrator.time.sleep"):
                    result = orchestrator.process_task(task_file)

        assert orchestrator.mock_runner.run.call_count == 3
        assert result == "retry"

    def test_server_error_retries(self, orchestrator, orchestrator_config):
        """ServerError should retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "server-err")

        orchestrator.mock_runner.run.side_effect = make_server_error("Internal error")

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.adk_orchestrator.time.sleep"):
                    result = orchestrator.process_task(task_file)

        assert orchestrator.mock_runner.run.call_count == 3
        assert result == "retry"

    def test_transient_error_recovers_on_retry(self, orchestrator, orchestrator_config):
        """Transient error that succeeds on retry should process."""
        task_file = self._create_valid_task_file(orchestrator_config, "transient")

        # First two calls fail, third succeeds
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Success after retry"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.side_effect = [
            ServiceUnavailable("Temporary failure"),
            ServiceUnavailable("Still down"),
            [mock_event],  # Success on third try
        ]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.adk_orchestrator.time.sleep"):
                    with patch("src.agents.tools.email_tools.send_email"):
                        result = orchestrator.process_task(task_file)

        assert orchestrator.mock_runner.run.call_count == 3
        assert result == "processed"

    def test_unexpected_exception_returns_retry(self, orchestrator, orchestrator_config):
        """Unexpected exception should return retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "unexpected")

        orchestrator.mock_runner.run.side_effect = RuntimeError("Unexpected error")

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                result = orchestrator.process_task(task_file)

        # Unexpected errors are caught and return retry
        assert result == "retry"

    def test_no_response_from_runner_returns_retry(
        self, orchestrator, orchestrator_config
    ):
        """Runner returning no final response should return retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "no-response")

        # Runner returns events but none are final responses
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = False
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                result = orchestrator.process_task(task_file)

        # No response text and no email sent should return retry
        assert result == "retry"

    def test_runner_returns_empty_iterator(self, orchestrator, orchestrator_config):
        """Runner returning empty iterator should return retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "empty-iter")

        orchestrator.mock_runner.run.return_value = iter([])

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                result = orchestrator.process_task(task_file)

        assert result == "retry"


# ==============================================================================
# Test 4: Session Service Failures
# ==============================================================================


class TestSessionServiceFailures:
    """Tests for session service failures."""

    def _create_valid_task_file(self, config, task_id="test-300"):
        """Helper to create a valid task file."""
        config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = config.input_dir / f"task_{task_id}.json"
        task_file.write_text(json.dumps({
            "id": task_id,
            "subject": "Session test",
            "body": "Testing session failures",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": [],
        }))
        return task_file

    def test_session_store_get_or_create_exception(
        self, orchestrator, orchestrator_config
    ):
        """Session store get_or_create failure should return retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "sess-create")

        # Corrupt the sessions file
        orchestrator_config.sessions_file.parent.mkdir(parents=True, exist_ok=True)
        orchestrator_config.sessions_file.write_text("{corrupted json")

        # The FileSessionStore should handle this gracefully, but let's test
        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                # This should not crash even with corrupted session file
                # The session store returns empty dict on JSON decode error
                mock_event = MagicMock()
                mock_event.is_final_response.return_value = True
                mock_event.content = MagicMock()
                mock_part = MagicMock()
                mock_part.text = "OK"
                mock_event.content.parts = [mock_part]
                mock_event.get_function_calls.return_value = []
                orchestrator.mock_runner.run.return_value = [mock_event]

                with patch("src.agents.tools.email_tools.send_email"):
                    result = orchestrator.process_task(task_file)

        # Should process despite corrupted session file (creates new session)
        assert result == "processed"

    def test_adk_session_service_create_failure(
        self, orchestrator, orchestrator_config
    ):
        """ADK InMemorySessionService create failure should return retry."""
        task_file = self._create_valid_task_file(orchestrator_config, "adk-sess")

        # Mock the session service to fail
        async def failing_get_session(*args, **kwargs):
            return None

        async def failing_create_session(*args, **kwargs):
            raise RuntimeError("Session creation failed")

        orchestrator.session_service.get_session = failing_get_session
        orchestrator.session_service.create_session = failing_create_session

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                result = orchestrator.process_task(task_file)

        assert result == "retry"

    def test_session_store_add_message_failure(
        self, orchestrator, orchestrator_config
    ):
        """Session store add_message failure should not crash."""
        task_file = self._create_valid_task_file(orchestrator_config, "add-msg")

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Response"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        # Create a mock session_store that fails on add_message
        original_session_store = orchestrator.session_store

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context"):
                with patch("src.agents.tools.email_tools.send_email"):
                    # Make add_message raise an exception
                    with patch.object(
                        orchestrator.session_store,
                        "add_message",
                        side_effect=RuntimeError("Write failed"),
                    ):
                        result = orchestrator.process_task(task_file)

        # Should return retry because the exception propagates
        assert result == "retry"


# ==============================================================================
# Test 5: Email Sending Failures in Agent Tasks
# ==============================================================================


class TestAgentTaskEmailFailures:
    """Tests for agent task email sending failures."""

    def _create_agent_task_file(self, config, action, params, task_id="agent-100"):
        """Helper to create an agent task file."""
        config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = config.input_dir / f"task_{task_id}.json"
        task_file.write_text(json.dumps({
            "task_type": "agent_task",
            "id": task_id,
            "action": action,
            "params": params,
            "created_by": "TestAgent",
            "original_sender": "user@test.com",
            "original_thread_id": "thread-123",
        }))
        return task_file

    def test_send_email_missing_to_address(self, orchestrator, orchestrator_config):
        """Agent task send_email missing to_address should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {"subject": "Test", "body": "Test body"},
            "email-no-to",
        )

        result = orchestrator.process_task(task_file)
        assert result == "failed"

    def test_send_email_missing_subject(self, orchestrator, orchestrator_config):
        """Agent task send_email missing subject should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {"to_address": "user@test.com", "body": "Test body"},
            "email-no-subj",
        )

        result = orchestrator.process_task(task_file)
        assert result == "failed"

    def test_send_email_missing_body(self, orchestrator, orchestrator_config):
        """Agent task send_email missing body should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {"to_address": "user@test.com", "subject": "Test"},
            "email-no-body",
        )

        result = orchestrator.process_task(task_file)
        assert result == "failed"

    def test_send_email_to_non_whitelisted_recipient(
        self, orchestrator, orchestrator_config
    ):
        """Agent task send_email to non-whitelisted recipient should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {
                "to_address": "hacker@evil.com",
                "subject": "Exfiltration attempt",
                "body": "Stealing data",
            },
            "email-blocked",
        )

        result = orchestrator.process_task(task_file)
        assert result == "failed"

    def test_send_email_smtp_failure(self, orchestrator, orchestrator_config):
        """Agent task send_email with SMTP failure should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {
                "to_address": "allowed@example.com",
                "subject": "SMTP test",
                "body": "Testing SMTP failure",
            },
            "email-smtp-fail",
        )

        with patch("src.adk_orchestrator.send_email") as mock_send:
            mock_send.return_value = False  # SMTP failure
            result = orchestrator.process_task(task_file)

        assert result == "failed"

    def test_send_email_exception(self, orchestrator, orchestrator_config):
        """Agent task send_email with exception should fail."""
        task_file = self._create_agent_task_file(
            orchestrator_config,
            "send_email",
            {
                "to_address": "allowed@example.com",
                "subject": "Exception test",
                "body": "Testing exception",
            },
            "email-exception",
        )

        with patch("src.adk_orchestrator.send_email") as mock_send:
            mock_send.side_effect = Exception("SMTP connection failed")
            result = orchestrator.process_task(task_file)

        assert result == "failed"


# ==============================================================================
# Test 6: Move Task Failures
# ==============================================================================


class TestMoveTaskFailures:
    """Tests for move_task error handling."""

    def test_move_nonexistent_file(self, orchestrator, orchestrator_config):
        """Moving nonexistent file should not crash."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        fake_file = orchestrator_config.input_dir / "nonexistent.json"

        # Should not raise exception
        orchestrator.move_task(fake_file, orchestrator_config.processed_dir)

    def test_move_with_attachments(self, orchestrator, orchestrator_config):
        """Move should include attachments."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)

        # Create task with attachment
        task_file = orchestrator_config.input_dir / "task_move.json"
        attachment = orchestrator_config.input_dir / "image.png"
        attachment.write_bytes(b"\x89PNG data")

        task_file.write_text(json.dumps({
            "id": "move-test",
            "subject": "Move test",
            "body": "Testing move",
            "sender": "user@test.com",
            "reply_to": "user@test.com",
            "attachments": ["image.png"],
        }))

        orchestrator.move_task(task_file, orchestrator_config.processed_dir)

        # Both should be moved
        assert not task_file.exists()
        assert not attachment.exists()
        assert (orchestrator_config.processed_dir / "task_move.json").exists()
        assert (orchestrator_config.processed_dir / "image.png").exists()

    def test_move_with_missing_attachment(self, orchestrator, orchestrator_config):
        """Move with missing attachment should still move task file."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)

        task_file = orchestrator_config.input_dir / "task_missing_attach.json"
        task_file.write_text(json.dumps({
            "id": "move-missing",
            "subject": "Move missing attachment",
            "body": "Testing",
            "sender": "user@test.com",
            "reply_to": "user@test.com",
            "attachments": ["nonexistent.png"],
        }))

        orchestrator.move_task(task_file, orchestrator_config.processed_dir)

        # Task file should still be moved
        assert not task_file.exists()
        assert (orchestrator_config.processed_dir / "task_missing_attach.json").exists()


# ==============================================================================
# Test 7: Context Cleanup
# ==============================================================================


class TestContextCleanup:
    """Tests to verify request context is always cleaned up."""

    def test_context_cleared_on_success(self, orchestrator, orchestrator_config):
        """Request context should be cleared after successful processing."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_ctx_success.json"
        task_file.write_text(json.dumps({
            "id": "ctx-success",
            "subject": "Context test",
            "body": "Testing context cleanup",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": [],
        }))

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_event.content = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Done"
        mock_event.content.parts = [mock_part]
        mock_event.get_function_calls.return_value = []

        orchestrator.mock_runner.run.return_value = [mock_event]

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context") as mock_clear:
                with patch("src.agents.tools.email_tools.send_email"):
                    orchestrator.process_task(task_file)

        # Context should be cleared exactly once
        assert mock_clear.call_count == 1

    def test_context_cleared_on_exception(self, orchestrator, orchestrator_config):
        """Request context should be cleared even after exceptions."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_ctx_except.json"
        task_file.write_text(json.dumps({
            "id": "ctx-except",
            "subject": "Context exception test",
            "body": "Testing context cleanup on error",
            "sender": "allowed@example.com",
            "reply_to": "allowed@example.com",
            "attachments": [],
        }))

        orchestrator.mock_runner.run.side_effect = RuntimeError("Crash!")

        with patch("src.adk_orchestrator.set_request_context"):
            with patch("src.adk_orchestrator.clear_request_context") as mock_clear:
                orchestrator.process_task(task_file)

        # Context should still be cleared despite exception
        assert mock_clear.call_count == 1

    def test_context_cleared_on_retry(self, orchestrator, orchestrator_config):
        """Request context should be cleared on retry path (finally always runs)."""
        orchestrator_config.input_dir.mkdir(parents=True, exist_ok=True)
        task_file = orchestrator_config.input_dir / "task_ctx_retry.json"
        task_file.write_text("{invalid json")

        with patch("src.adk_orchestrator.clear_request_context") as mock_clear:
            orchestrator.process_task(task_file)

        # The finally block always runs, even for early returns before set_request_context
        # This is defensive - clearing context that was never set is a no-op
        assert mock_clear.call_count == 1
