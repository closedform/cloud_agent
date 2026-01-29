"""Tests for task creation with request context requirements.

Tests the interaction between task_tools.py and _context.py, specifically:
1. What happens when get_user_email() returns None vs empty string
2. What happens when get_thread_id() returns None vs empty string
3. Can tasks be created from a background thread with no context
4. What happens if context is cleared mid-execution
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.tools._context import (
    clear_request_context,
    get_request_context,
    get_thread_id,
    get_user_email,
    set_request_context,
)
from src.agents.tools.task_tools import create_agent_task


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_context():
    """Reset global context before and after each test."""
    clear_request_context()
    yield
    clear_request_context()


@pytest.fixture
def mock_config(temp_dir: Path):
    """Create mock config with temp directory."""
    config = MagicMock()
    config.input_dir = temp_dir / "inputs"
    config.input_dir.mkdir(parents=True, exist_ok=True)
    config.allowed_senders = ("allowed@example.com", "other@example.com")
    return config


# =============================================================================
# Test 1: get_user_email() returns None vs empty string
# =============================================================================


class TestUserEmailBehavior:
    """Tests for get_user_email() return value handling in task creation."""

    def test_get_user_email_returns_empty_string_not_none_when_unset(self):
        """get_user_email() should return empty string, not None, when context not set."""
        clear_request_context()
        result = get_user_email()

        # Verify it's an empty string, not None
        assert result is not None
        assert result == ""
        assert isinstance(result, str)

    def test_get_user_email_returns_empty_string_after_clear(self):
        """get_user_email() returns empty string after context is cleared."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )
        clear_request_context()
        result = get_user_email()

        assert result == ""
        assert result is not None

    def test_create_task_fails_with_empty_user_email(self, mock_config):
        """create_agent_task should fail when user_email is empty string."""
        clear_request_context()

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        assert "No user context" in result["message"]

    def test_create_task_fails_when_context_set_with_empty_email(self, mock_config):
        """create_agent_task should fail when context explicitly set with empty email."""
        set_request_context(
            user_email="",  # Explicitly empty
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        assert "No user context" in result["message"]

    def test_create_task_succeeds_with_valid_email(self, mock_config):
        """create_agent_task should succeed with valid user email.

        Note: The user email must be in allowed_senders for security.
        """
        set_request_context(
            user_email="allowed@example.com",  # Must be in allowed_senders
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "other@example.com",  # Recipient must also be allowed
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "success"


# =============================================================================
# Test 2: get_thread_id() returns None vs empty string
# =============================================================================


class TestThreadIdBehavior:
    """Tests for get_thread_id() return value handling in task creation."""

    def test_get_thread_id_returns_empty_string_not_none_when_unset(self):
        """get_thread_id() should return empty string, not None, when context not set."""
        clear_request_context()
        result = get_thread_id()

        assert result is not None
        assert result == ""
        assert isinstance(result, str)

    def test_get_thread_id_returns_empty_string_after_clear(self):
        """get_thread_id() returns empty string after context is cleared."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )
        clear_request_context()
        result = get_thread_id()

        assert result == ""
        assert result is not None

    def test_task_created_with_empty_thread_id_when_valid_email(self, mock_config):
        """Task can be created with empty thread_id if user_email is valid.

        Note: The user email must be in allowed_senders for security.
        """
        set_request_context(
            user_email="allowed@example.com",  # Must be in allowed_senders
            thread_id="",  # Explicitly empty
            reply_to="reply@example.com",
        )

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "other@example.com",  # Recipient must also be allowed
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        # Task should succeed - only user_email is required
        assert result["status"] == "success"

        # Verify the task file has empty thread_id
        task_files = list(mock_config.input_dir.glob("task_*.json"))
        assert len(task_files) == 1
        with open(task_files[0]) as f:
            task_data = json.load(f)
        assert task_data["original_thread_id"] == ""

    def test_task_created_with_none_thread_id_stored_as_none_in_json(self, mock_config):
        """Verify behavior when thread_id could theoretically be None.

        Note: The task is written with None thread_id to the JSON file (null).
        However, when AgentTask.from_dict() deserializes it, None is converted
        to empty string for type safety.
        """
        set_request_context(
            user_email="allowed@example.com",  # Must be in allowed_senders
            thread_id="valid-thread",
            reply_to="reply@example.com",
        )

        # Even if we patched get_thread_id to return None, the task would still be created
        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch("src.agents.tools.task_tools.get_thread_id", return_value=None):
                result = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "other@example.com",  # Recipient must also be allowed
                        "subject": "Test",
                        "body": "Hello",
                    },
                    created_by="TestAgent",
                )

        assert result["status"] == "success"

        # Verify the task file has None stored (json null) in the raw JSON
        task_files = list(mock_config.input_dir.glob("task_*.json"))
        assert len(task_files) == 1
        with open(task_files[0]) as f:
            task_data = json.load(f)
        # Raw JSON has null (Python None) because create_agent_task stores it directly
        assert task_data["original_thread_id"] is None

        # But when deserialized via AgentTask.from_dict, None becomes empty string
        from src.models import AgentTask
        task = AgentTask.from_dict(task_data)
        assert task.original_thread_id == ""


# =============================================================================
# Test 3: Tasks from background threads with no context
# =============================================================================


class TestBackgroundThreadNoContext:
    """Tests for task creation from background threads without context.

    Note: The implementation uses a shared dict (not thread-local), so all threads
    share the same context. This means background threads will see whatever context
    was set by the main thread (or other threads).
    """

    def test_background_thread_sees_shared_context(self, mock_config):
        """Background thread should see context set by main thread (shared dict)."""
        # Set context in main thread
        set_request_context(
            user_email="main@example.com",
            thread_id="main-thread",
            reply_to="main-reply@example.com",
        )

        results = {}

        def background_worker():
            # Read context from background thread
            results["email"] = get_user_email()
            results["thread_id"] = get_thread_id()

        t = threading.Thread(target=background_worker)
        t.start()
        t.join()

        # Background thread sees main thread's context (shared dict)
        assert results["email"] == "main@example.com"
        assert results["thread_id"] == "main-thread"

    def test_background_thread_fails_without_any_context(self, mock_config):
        """Background thread should fail to create task when no context exists."""
        clear_request_context()

        results = {}

        def background_worker():
            with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
                results["result"] = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "allowed@example.com",
                        "subject": "Test",
                        "body": "Hello",
                    },
                    created_by="BackgroundAgent",
                )

        t = threading.Thread(target=background_worker)
        t.start()
        t.join()

        assert results["result"]["status"] == "error"
        assert "No user context" in results["result"]["message"]

    def test_background_thread_can_create_task_with_shared_context(self, mock_config):
        """Background thread can create task when main thread set context.

        Note: The user email must be in allowed_senders for security.
        """
        # Main thread sets context with an allowed sender
        set_request_context(
            user_email="allowed@example.com",  # Must be in allowed_senders
            thread_id="main-thread",
            reply_to="main-reply@example.com",
        )

        results = {}

        def background_worker():
            with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
                results["result"] = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "other@example.com",  # Recipient must also be allowed
                        "subject": "Test",
                        "body": "Hello",
                    },
                    created_by="BackgroundAgent",
                )

        t = threading.Thread(target=background_worker)
        t.start()
        t.join()

        # Should succeed because context is shared
        assert results["result"]["status"] == "success"

    def test_multiple_background_threads_share_context(self, mock_config):
        """Multiple background threads all see the same shared context."""
        set_request_context(
            user_email="shared@example.com",
            thread_id="shared-thread",
            reply_to="shared-reply@example.com",
        )

        results = {}
        barrier = threading.Barrier(3)

        def worker(worker_id: int):
            barrier.wait()  # Synchronize threads
            results[worker_id] = {
                "email": get_user_email(),
                "thread_id": get_thread_id(),
            }

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should see the same context
        for i in range(3):
            assert results[i]["email"] == "shared@example.com"
            assert results[i]["thread_id"] == "shared-thread"


# =============================================================================
# Test 4: Context cleared mid-execution
# =============================================================================


class TestContextClearedMidExecution:
    """Tests for what happens when context is cleared during task operations."""

    def test_context_cleared_before_task_creation_fails(self, mock_config):
        """If context is cleared before get_user_email() is called, task fails."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        # Clear before calling create_agent_task
        clear_request_context()

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "error"
        assert "No user context" in result["message"]

    def test_concurrent_clear_during_task_creation(self, mock_config):
        """Test race condition: context cleared while task is being created."""
        results = {}
        errors = []

        def task_creator():
            """Creates tasks in a loop."""
            for i in range(20):
                set_request_context(
                    user_email=f"user{i}@example.com",
                    thread_id=f"thread-{i}",
                    reply_to=f"reply{i}@example.com",
                )
                with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": f"Test {i}",
                            "body": f"Hello {i}",
                        },
                        created_by="TestAgent",
                    )
                results[f"task_{i}"] = result

        def context_clearer():
            """Clears context repeatedly."""
            for _ in range(50):
                time.sleep(0.001)  # Small delay
                clear_request_context()

        # Run both threads concurrently
        t1 = threading.Thread(target=task_creator)
        t2 = threading.Thread(target=context_clearer)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Some tasks may succeed, some may fail - this tests for crashes
        # The important thing is no exceptions were raised
        success_count = sum(1 for r in results.values() if r["status"] == "success")
        error_count = sum(1 for r in results.values() if r["status"] == "error")

        # Verify we got results for all attempts
        assert len(results) == 20
        # At least some should have succeeded or failed gracefully
        assert success_count + error_count == 20

    def test_context_read_then_cleared_values_captured(self, mock_config):
        """Values captured from context before clear are preserved."""
        set_request_context(
            user_email="captured@example.com",
            thread_id="captured-thread",
            reply_to="captured-reply@example.com",
        )

        # Capture values
        captured_email = get_user_email()
        captured_thread = get_thread_id()

        # Clear context
        clear_request_context()

        # Original captured values should still be valid
        assert captured_email == "captured@example.com"
        assert captured_thread == "captured-thread"

        # But fresh reads should return empty
        assert get_user_email() == ""
        assert get_thread_id() == ""


# =============================================================================
# Additional edge cases
# =============================================================================


class TestEdgeCases:
    """Additional edge cases for context and task creation."""

    def test_context_with_special_characters_preserved(self, mock_config):
        """Special characters in context values should be preserved in tasks.

        Note: The user email must be in allowed_senders for security.
        We add a special-character email to the allowed list for this test.
        """
        # Update mock config to include the special email
        mock_config.allowed_senders = (
            "allowed@example.com",
            "other@example.com",
            "user+special@example.com",
        )

        set_request_context(
            user_email="user+special@example.com",
            thread_id="thread-with-dashes_and_underscores",
            reply_to="reply+test@example.com",
        )

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        assert result["status"] == "success"

        # Verify task file preserves special characters
        task_files = list(mock_config.input_dir.glob("task_*.json"))
        with open(task_files[0]) as f:
            task_data = json.load(f)
        assert task_data["original_sender"] == "user+special@example.com"
        assert task_data["original_thread_id"] == "thread-with-dashes_and_underscores"

    def test_whitespace_only_email_treated_as_empty(self, mock_config):
        """Whitespace-only user_email should not be treated as valid.

        The implementation correctly strips whitespace and treats it as empty.
        """
        set_request_context(
            user_email="   ",  # Whitespace only
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
                created_by="TestAgent",
            )

        # Whitespace-only email is correctly rejected
        assert result["status"] == "error"
        assert "user context" in result["message"].lower()

    def test_rapid_context_switches(self, mock_config):
        """Rapid context switches should maintain consistency."""
        for i in range(100):
            set_request_context(
                user_email=f"user{i}@example.com",
                thread_id=f"thread-{i}",
                reply_to=f"reply{i}@example.com",
            )

            # Immediately read back
            email = get_user_email()
            thread_id = get_thread_id()

            assert email == f"user{i}@example.com"
            assert thread_id == f"thread-{i}"

    def test_context_after_multiple_clears(self, mock_config):
        """Multiple clears should leave context in clean state."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        # Multiple clears
        clear_request_context()
        clear_request_context()
        clear_request_context()

        # Should be clean
        assert get_user_email() == ""
        assert get_thread_id() == ""

        # Full context should be empty
        context = get_request_context()
        assert context == {
            "user_email": "",
            "thread_id": "",
            "reply_to": "",
            "body": "",
        }
