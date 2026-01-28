"""Tests for src/agents/tools/_context.py - Thread-safe global context management."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

import pytest

from src.agents.tools._context import (
    _request_context,
    _services,
    clear_request_context,
    get_request_context,
    get_services,
    set_request_context,
    set_services,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_context():
    """Reset global context before and after each test."""
    # Clear before test
    clear_request_context()
    # Reset services to None
    import src.agents.tools._context as ctx

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
# Tests for thread-local isolation
# =============================================================================


class TestThreadLocalIsolation:
    """Tests for thread-local isolation of request context."""

    def test_different_threads_have_isolated_context(self):
        """Each thread should have its own isolated request context."""
        results = {}
        barrier = threading.Barrier(3)

        def thread_worker(thread_id: str):
            # Set context for this thread
            set_request_context(
                user_email=f"user{thread_id}@example.com",
                thread_id=f"thread-{thread_id}",
                reply_to=f"reply{thread_id}@example.com",
                body=f"Body for thread {thread_id}",
            )

            # Wait for all threads to set their context
            barrier.wait()

            # Small delay to allow potential interference
            time.sleep(0.01)

            # Read back context - should still be our values
            context = get_request_context()
            results[thread_id] = context

        threads = [
            threading.Thread(target=thread_worker, args=(str(i),)) for i in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify each thread got its own context
        for thread_id in ["0", "1", "2"]:
            assert results[thread_id]["user_email"] == f"user{thread_id}@example.com"
            assert results[thread_id]["thread_id"] == f"thread-{thread_id}"
            assert results[thread_id]["reply_to"] == f"reply{thread_id}@example.com"
            assert results[thread_id]["body"] == f"Body for thread {thread_id}"

    def test_thread_pool_executor_isolation(self):
        """ThreadPoolExecutor workers should have isolated contexts."""
        results = {}

        def worker(worker_id: int) -> dict:
            # Set unique context for this worker
            set_request_context(
                user_email=f"worker{worker_id}@example.com",
                thread_id=f"thread-{worker_id}",
                reply_to=f"reply{worker_id}@example.com",
                body=f"Body {worker_id}",
            )

            # Simulate some work
            time.sleep(0.01)

            # Return the context we read
            return {"worker_id": worker_id, "context": get_request_context()}

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]

            for future in as_completed(futures):
                result = future.result()
                worker_id = result["worker_id"]
                context = result["context"]

                # Each worker should see its own context
                assert context["user_email"] == f"worker{worker_id}@example.com"
                assert context["thread_id"] == f"thread-{worker_id}"
                results[worker_id] = context

        assert len(results) == 10

    def test_main_thread_unaffected_by_worker_threads(self):
        """Main thread context should not be affected by worker threads."""
        # Set context in main thread
        set_request_context(
            user_email="main@example.com",
            thread_id="main-thread",
            reply_to="main-reply@example.com",
            body="Main thread body",
        )

        def worker():
            set_request_context(
                user_email="worker@example.com",
                thread_id="worker-thread",
                reply_to="worker@example.com",
                body="Worker body",
            )
            time.sleep(0.01)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Main thread context should be unchanged
        result = get_request_context()
        assert result["user_email"] == "main@example.com"
        assert result["thread_id"] == "main-thread"
        assert result["reply_to"] == "main-reply@example.com"
        assert result["body"] == "Main thread body"

    def test_clearing_context_in_one_thread_does_not_affect_others(self):
        """Clearing context in one thread should not affect other threads."""
        results = {}
        barrier = threading.Barrier(2)
        clear_event = threading.Event()

        def setter_thread():
            set_request_context(
                user_email="setter@example.com",
                thread_id="setter-thread",
                reply_to="setter@example.com",
                body="Setter body",
            )
            barrier.wait()  # Signal ready
            clear_event.wait()  # Wait for clearer to clear
            time.sleep(0.01)  # Give time for clear to complete
            results["setter"] = get_request_context()

        def clearer_thread():
            set_request_context(
                user_email="clearer@example.com",
                thread_id="clearer-thread",
                reply_to="clearer@example.com",
                body="Clearer body",
            )
            barrier.wait()  # Wait for setter
            clear_request_context()  # Clear our own context
            clear_event.set()  # Signal that we've cleared
            results["clearer"] = get_request_context()

        t1 = threading.Thread(target=setter_thread)
        t2 = threading.Thread(target=clearer_thread)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Setter thread should still have its context
        assert results["setter"]["user_email"] == "setter@example.com"

        # Clearer thread should have empty context
        assert results["clearer"]["user_email"] == ""

    def test_new_thread_has_default_context(self):
        """A new thread should start with default (empty) context."""
        # Set context in main thread
        set_request_context(
            user_email="main@example.com",
            thread_id="main-thread",
            reply_to="main@example.com",
            body="Main body",
        )

        new_thread_context = {}

        def new_thread():
            # Don't set any context - just read
            new_thread_context.update(get_request_context())

        t = threading.Thread(target=new_thread)
        t.start()
        t.join()

        # New thread should have empty context
        assert new_thread_context == {
            "user_email": "",
            "thread_id": "",
            "reply_to": "",
            "body": "",
        }


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
        """If thread-local attributes are missing, defaults should be returned."""
        # Directly manipulate thread-local to simulate partial state
        _request_context.user_email = "partial@example.com"
        # Don't set thread_id, reply_to, body

        result = get_request_context()

        assert result["user_email"] == "partial@example.com"
        assert result["thread_id"] == ""
        assert result["reply_to"] == ""
        assert result["body"] == ""


# =============================================================================
# Integration tests
# =============================================================================


class TestIntegration:
    """Integration tests combining services and request context."""

    def test_services_and_context_independent(self, mock_services):
        """Services (global) and request context (thread-local) should be independent."""
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

    def test_concurrent_services_and_context_operations(self, mock_services):
        """Concurrent operations on services and context should not interfere."""
        set_services(mock_services)
        errors = []

        def worker(worker_id: int):
            try:
                for _ in range(50):
                    # Set and get request context
                    set_request_context(
                        user_email=f"worker{worker_id}@example.com",
                        thread_id=f"thread-{worker_id}",
                        reply_to=f"reply{worker_id}@example.com",
                        body=f"Body {worker_id}",
                    )

                    context = get_request_context()
                    if context["user_email"] != f"worker{worker_id}@example.com":
                        errors.append(f"Context mismatch in worker {worker_id}")

                    # Get services (should always return the same mock)
                    svc = get_services()
                    if svc is not mock_services:
                        errors.append(f"Services mismatch in worker {worker_id}")

                    # Clear and verify
                    clear_request_context()
                    if get_request_context()["user_email"] != "":
                        errors.append(f"Clear failed in worker {worker_id}")

            except Exception as e:
                errors.append(f"Exception in worker {worker_id}: {e}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        assert len(errors) == 0, f"Errors occurred: {errors}"
