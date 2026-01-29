"""Tests for src/agents/tools/_context.py - Thread-safe global context management.

Design Notes:
- Services: Global singleton, thread-safe read/write
- Request Context: Shared dict (NOT thread-local) for ADK sub-agent access
  ADK runs sub-agents in separate threads that need the SAME context values.
  Tasks are processed sequentially, so only one context is active at a time.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

import pytest

from src.agents.tools._context import (
    clear_request_context,
    get_body,
    get_reply_to,
    get_request_context,
    get_services,
    get_thread_id,
    get_user_email,
    set_request_context,
    set_services,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_context():
    """Reset global context before and after each test."""
    import src.agents.tools._context as ctx

    # Clear before test
    clear_request_context()
    # Reset services to None
    with ctx._lock:
        ctx._services = None

    yield

    # Clear after test
    clear_request_context()
    with ctx._lock:
        ctx._services = None


@pytest.fixture
def mock_services():
    """Create a mock services instance."""
    services = MagicMock()
    services.gemini_client = MagicMock()
    services.calendar_service = MagicMock()
    services.calendars = {"primary": "primary@calendar.google.com"}
    return services


# =============================================================================
# Tests for set_services() and get_services()
# =============================================================================


class TestServices:
    """Tests for services getter and setter."""

    def test_get_services_returns_none_when_not_set(self):
        """get_services() should return None when services haven't been set."""
        result = get_services()
        assert result is None

    def test_set_services_stores_instance(self, mock_services):
        """set_services() should store the services instance."""
        set_services(mock_services)
        result = get_services()
        assert result is mock_services

    def test_set_services_replaces_existing(self, mock_services):
        """set_services() should replace existing services instance."""
        first_services = MagicMock()
        first_services.name = "first"

        second_services = MagicMock()
        second_services.name = "second"

        set_services(first_services)
        assert get_services().name == "first"

        set_services(second_services)
        assert get_services().name == "second"

    def test_services_thread_safe_access(self, mock_services):
        """Services should be accessible safely from multiple threads."""
        set_services(mock_services)
        results = []
        errors = []

        def read_services():
            try:
                for _ in range(100):
                    svc = get_services()
                    if svc is not mock_services:
                        errors.append(f"Unexpected services: {svc}")
                    results.append(svc)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_services) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 1000
        assert all(r is mock_services for r in results)


# =============================================================================
# Tests for set_request_context() and get_request_context()
# =============================================================================


class TestRequestContext:
    """Tests for request context getter and setter."""

    def test_get_request_context_returns_defaults_when_not_set(self):
        """get_request_context() should return empty strings when context not set."""
        result = get_request_context()

        assert result == {
            "user_email": "",
            "thread_id": "",
            "reply_to": "",
            "body": "",
        }

    def test_set_request_context_stores_values(self):
        """set_request_context() should store all provided values."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Hello world",
        )

        result = get_request_context()

        assert result == {
            "user_email": "user@example.com",
            "thread_id": "thread-123",
            "reply_to": "reply@example.com",
            "body": "Hello world",
        }

    def test_set_request_context_with_default_body(self):
        """set_request_context() should use empty string for body if not provided."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
        )

        result = get_request_context()

        assert result["body"] == ""
        assert result["user_email"] == "user@example.com"

    def test_set_request_context_replaces_existing(self):
        """set_request_context() should replace existing context values."""
        set_request_context(
            user_email="first@example.com",
            thread_id="thread-1",
            reply_to="first@example.com",
            body="First message",
        )

        set_request_context(
            user_email="second@example.com",
            thread_id="thread-2",
            reply_to="second@example.com",
            body="Second message",
        )

        result = get_request_context()

        assert result["user_email"] == "second@example.com"
        assert result["thread_id"] == "thread-2"
        assert result["reply_to"] == "second@example.com"
        assert result["body"] == "Second message"

    def test_request_context_handles_special_characters(self):
        """Request context should handle special characters in values."""
        set_request_context(
            user_email="user+test@example.com",
            thread_id="thread-with-dashes_and_underscores",
            reply_to="reply@example.com",
            body="Body with\nnewlines\tand\ttabs",
        )

        result = get_request_context()

        assert result["user_email"] == "user+test@example.com"
        assert result["body"] == "Body with\nnewlines\tand\ttabs"

    def test_request_context_handles_empty_strings(self):
        """Request context should handle empty strings properly."""
        set_request_context(
            user_email="",
            thread_id="",
            reply_to="",
            body="",
        )

        result = get_request_context()

        assert all(v == "" for v in result.values())


# =============================================================================
# Tests for clear_request_context()
# =============================================================================


class TestClearRequestContext:
    """Tests for clearing request context."""

    def test_clear_request_context_resets_all_values(self):
        """clear_request_context() should reset all values to empty strings."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Some body content",
        )

        clear_request_context()

        result = get_request_context()
        assert result == {
            "user_email": "",
            "thread_id": "",
            "reply_to": "",
            "body": "",
        }

    def test_clear_request_context_idempotent(self):
        """clear_request_context() should be safe to call multiple times."""
        clear_request_context()
        clear_request_context()
        clear_request_context()

        result = get_request_context()
        assert result == {
            "user_email": "",
            "thread_id": "",
            "reply_to": "",
            "body": "",
        }

    def test_clear_and_set_cycle(self):
        """Context should work correctly through set/clear cycles."""
        for i in range(5):
            set_request_context(
                user_email=f"user{i}@example.com",
                thread_id=f"thread-{i}",
                reply_to=f"reply{i}@example.com",
                body=f"Body {i}",
            )

            result = get_request_context()
            assert result["user_email"] == f"user{i}@example.com"

            clear_request_context()

            result = get_request_context()
            assert result["user_email"] == ""


# =============================================================================
# Tests for shared context (ADK design)
# =============================================================================


class TestSharedContext:
    """Tests for shared context behavior (ADK sub-agent design).

    The request context is intentionally SHARED across threads, not isolated.
    This is because ADK runs sub-agents in separate threads that need access
    to the same context values set by the orchestrator. Tasks are processed
    sequentially, so only one context is active at any time.
    """

    def test_context_shared_across_threads(self):
        """Context should be shared across threads (ADK sub-agent pattern)."""
        # Orchestrator sets context in main thread
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Original request body",
        )

        sub_agent_context = {}

        def sub_agent_thread():
            # Sub-agent reads the same context (simulating ADK sub-agent)
            sub_agent_context.update(get_request_context())

        t = threading.Thread(target=sub_agent_thread)
        t.start()
        t.join()

        # Sub-agent should see the orchestrator's context
        assert sub_agent_context["user_email"] == "user@example.com"
        assert sub_agent_context["thread_id"] == "thread-123"
        assert sub_agent_context["reply_to"] == "reply@example.com"
        assert sub_agent_context["body"] == "Original request body"

    def test_sub_agent_sees_latest_context(self):
        """Sub-agent threads should see the latest context values."""
        results = []

        def sub_agent_reader():
            # Small delay to ensure main thread has set context
            time.sleep(0.01)
            results.append(get_request_context())

        # Start sub-agent thread before setting context
        t = threading.Thread(target=sub_agent_reader)
        t.start()

        # Orchestrator sets context
        set_request_context(
            user_email="orchestrator@example.com",
            thread_id="orchestrator-thread",
            reply_to="orchestrator@example.com",
            body="Orchestrator body",
        )

        t.join()

        # Sub-agent should have read the context set by orchestrator
        assert len(results) == 1
        assert results[0]["user_email"] == "orchestrator@example.com"

    def test_clear_context_affects_all_threads(self):
        """Clearing context should affect all threads (shared state)."""
        # Set context
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Some body",
        )

        results = {}
        barrier = threading.Barrier(2)

        def reader_thread():
            barrier.wait()  # Wait for clear
            results["after_clear"] = get_request_context()

        t = threading.Thread(target=reader_thread)
        t.start()

        # Clear context
        clear_request_context()
        barrier.wait()  # Signal reader

        t.join()

        # Reader should see cleared context
        assert results["after_clear"]["user_email"] == ""
        assert results["after_clear"]["thread_id"] == ""

    def test_sequential_task_processing_pattern(self):
        """Simulate sequential task processing with context per task."""
        results = []

        def process_task(task_id: int) -> dict:
            """Simulate orchestrator processing a task."""
            # Set context for this task
            set_request_context(
                user_email=f"user{task_id}@example.com",
                thread_id=f"thread-{task_id}",
                reply_to=f"reply{task_id}@example.com",
                body=f"Body for task {task_id}",
            )

            # Simulate sub-agent reading context
            context = get_request_context()

            # Clear context after task
            clear_request_context()

            return {"task_id": task_id, "context": context}

        # Process tasks sequentially (as the orchestrator does)
        for i in range(5):
            result = process_task(i)
            results.append(result)

        # Each task should have gotten its own context
        for i, result in enumerate(results):
            assert result["context"]["user_email"] == f"user{i}@example.com"
            assert result["context"]["thread_id"] == f"thread-{i}"

    def test_concurrent_reads_are_safe(self):
        """Multiple threads reading context concurrently should be safe."""
        set_request_context(
            user_email="shared@example.com",
            thread_id="shared-thread",
            reply_to="shared@example.com",
            body="Shared body",
        )

        results = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    ctx = get_request_context()
                    if ctx["user_email"] != "shared@example.com":
                        errors.append(f"Unexpected email: {ctx['user_email']}")
                    results.append(ctx)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 1000
        assert all(r["user_email"] == "shared@example.com" for r in results)


# =============================================================================
# Tests for default values
# =============================================================================


class TestDefaultValues:
    """Tests for default values when context is not set."""

    def test_get_services_default_is_none(self):
        """get_services() default should be None."""
        import src.agents.tools._context as ctx

        with ctx._lock:
            ctx._services = None

        assert get_services() is None

    def test_get_request_context_default_values(self):
        """get_request_context() should return empty strings for all keys."""
        result = get_request_context()

        assert isinstance(result, dict)
        assert len(result) == 4
        assert "user_email" in result
        assert "thread_id" in result
        assert "reply_to" in result
        assert "body" in result
        assert all(isinstance(v, str) for v in result.values())
        assert all(v == "" for v in result.values())

    def test_partial_context_returns_defaults_for_unset(self):
        """If some context keys are missing, defaults should be returned."""
        import src.agents.tools._context as ctx

        # Directly manipulate shared dict to simulate partial state
        with ctx._context_lock:
            ctx._request_context["user_email"] = "partial@example.com"
            # Don't set thread_id, reply_to, body

        result = get_request_context()

        assert result["user_email"] == "partial@example.com"
        assert result["thread_id"] == ""
        assert result["reply_to"] == ""
        assert result["body"] == ""


# =============================================================================
# Tests for convenience accessors
# =============================================================================


class TestConvenienceAccessors:
    """Tests for convenience accessor functions."""

    def test_get_user_email(self):
        """get_user_email() should return user email from context."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Test body",
        )

        assert get_user_email() == "user@example.com"

    def test_get_user_email_default(self):
        """get_user_email() should return empty string when not set."""
        assert get_user_email() == ""

    def test_get_reply_to(self):
        """get_reply_to() should return reply-to address from context."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Test body",
        )

        assert get_reply_to() == "reply@example.com"

    def test_get_reply_to_default(self):
        """get_reply_to() should return empty string when not set."""
        assert get_reply_to() == ""

    def test_get_thread_id(self):
        """get_thread_id() should return thread ID from context."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Test body",
        )

        assert get_thread_id() == "thread-123"

    def test_get_thread_id_default(self):
        """get_thread_id() should return empty string when not set."""
        assert get_thread_id() == ""

    def test_get_body(self):
        """get_body() should return message body from context."""
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-123",
            reply_to="reply@example.com",
            body="Test body content",
        )

        assert get_body() == "Test body content"

    def test_get_body_default(self):
        """get_body() should return empty string when not set."""
        assert get_body() == ""


# =============================================================================
# Integration tests
# =============================================================================


class TestIntegration:
    """Integration tests combining services and request context."""

    def test_services_and_context_independent(self, mock_services):
        """Services (global) and request context (shared) should be independent."""
        # Set services
        set_services(mock_services)

        # Set request context
        set_request_context(
            user_email="user@example.com",
            thread_id="thread-1",
            reply_to="reply@example.com",
            body="Test body",
        )

        # Clear request context
        clear_request_context()

        # Services should still be set
        assert get_services() is mock_services

        # Request context should be cleared
        assert get_request_context()["user_email"] == ""

    def test_concurrent_services_access_is_safe(self, mock_services):
        """Concurrent access to services should be thread-safe."""
        set_services(mock_services)
        errors = []

        def worker(worker_id: int):
            try:
                for _ in range(100):
                    # Get services (should always return the same mock)
                    svc = get_services()
                    if svc is not mock_services:
                        errors.append(f"Services mismatch in worker {worker_id}")
            except Exception as e:
                errors.append(f"Exception in worker {worker_id}: {e}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_sequential_context_with_services(self, mock_services):
        """Sequential context operations with services should work correctly."""
        set_services(mock_services)

        # Simulate processing 5 tasks sequentially
        for i in range(5):
            set_request_context(
                user_email=f"user{i}@example.com",
                thread_id=f"thread-{i}",
                reply_to=f"reply{i}@example.com",
                body=f"Body {i}",
            )

            # Verify context
            ctx = get_request_context()
            assert ctx["user_email"] == f"user{i}@example.com"
            assert ctx["thread_id"] == f"thread-{i}"

            # Verify services still accessible
            assert get_services() is mock_services

            # Clear context (as orchestrator does after each task)
            clear_request_context()
            assert get_request_context()["user_email"] == ""
