"""Concurrency tests for task file handling.

Tests for race conditions in:
- src/task_io.py (atomic file operations)
- src/agents/tools/task_tools.py (create_agent_task)
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents.tools._context import clear_request_context, set_request_context
from src.task_io import read_task_safe, write_task_atomic


class TestConcurrentWriteTaskAtomic:
    """Test concurrent writes using write_task_atomic."""

    def test_concurrent_writes_to_different_files(self, temp_dir):
        """Many concurrent writes to different files should all succeed."""
        num_tasks = 100
        results = []
        errors = []

        def write_task(task_id: int) -> dict[str, Any]:
            task = {"id": f"task-{task_id}", "data": f"content-{task_id}"}
            path = temp_dir / f"task_{task_id}.json"
            try:
                write_task_atomic(task, path)
                return {"id": task_id, "success": True, "path": path}
            except Exception as e:
                return {"id": task_id, "success": False, "error": str(e)}

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(write_task, i) for i in range(num_tasks)]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if not result["success"]:
                    errors.append(result)

        # All writes should succeed
        assert len(errors) == 0, f"Failed writes: {errors}"
        assert len(results) == num_tasks

        # Verify all files exist and contain correct data
        for i in range(num_tasks):
            path = temp_dir / f"task_{i}.json"
            assert path.exists(), f"Missing file: {path}"
            loaded = read_task_safe(path)
            assert loaded is not None, f"Failed to read: {path}"
            assert loaded["id"] == f"task-{i}"
            assert loaded["data"] == f"content-{i}"

    def test_concurrent_writes_to_same_file(self, temp_dir):
        """Multiple writers to same file should not corrupt data."""
        path = temp_dir / "shared_task.json"
        num_writers = 50
        write_order = []
        lock = threading.Lock()

        def write_task(writer_id: int) -> None:
            task = {"writer": writer_id, "timestamp": time.time()}
            write_task_atomic(task, path)
            with lock:
                write_order.append(writer_id)

        threads = [
            threading.Thread(target=write_task, args=(i,)) for i in range(num_writers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All writers should complete
        assert len(write_order) == num_writers

        # File should contain valid JSON (last writer wins)
        loaded = read_task_safe(path)
        assert loaded is not None, "File should contain valid JSON"
        assert "writer" in loaded
        assert "timestamp" in loaded

    def test_no_temp_files_remain_after_concurrent_writes(self, temp_dir):
        """Concurrent writes should not leave temp files."""
        num_tasks = 50

        def write_task(task_id: int) -> None:
            task = {"id": f"task-{task_id}"}
            path = temp_dir / f"task_{task_id}.json"
            write_task_atomic(task, path)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_task, i) for i in range(num_tasks)]
            for future in as_completed(futures):
                future.result()

        # No temp files should remain
        tmp_files = list(temp_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Temp files remaining: {tmp_files}"

    def test_concurrent_read_during_write(self, temp_dir):
        """Reads during concurrent writes should return valid data or None."""
        path = temp_dir / "task.json"
        num_writes = 100
        num_reads = 200
        write_complete = threading.Event()
        read_results = []
        lock = threading.Lock()

        def writer():
            for i in range(num_writes):
                task = {"iteration": i, "data": "x" * 1000}
                write_task_atomic(task, path)
                time.sleep(0.001)  # Small delay to allow interleaving
            write_complete.set()

        def reader():
            while not write_complete.is_set() or len(read_results) < num_reads:
                result = read_task_safe(path)
                with lock:
                    read_results.append(result)
                    if len(read_results) >= num_reads:
                        break
                time.sleep(0.001)

        write_thread = threading.Thread(target=writer)
        read_threads = [threading.Thread(target=reader) for _ in range(5)]

        write_thread.start()
        for t in read_threads:
            t.start()

        write_thread.join()
        for t in read_threads:
            t.join()

        # Each read should return either None or valid data
        for result in read_results:
            if result is not None:
                assert "iteration" in result
                assert "data" in result


class TestConcurrentCreateAgentTask:
    """Test concurrent create_agent_task calls."""

    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create mock config for testing."""
        config = MagicMock()
        config.input_dir = temp_dir / "inputs"
        config.allowed_senders = ("allowed@example.com", "user@example.com")
        return config

    @pytest.fixture(autouse=True)
    def setup_context(self):
        """Set up request context before each test."""
        set_request_context(
            user_email="allowed@example.com",
            thread_id="test-thread-123",
            reply_to="allowed@example.com",
            body="test body",
        )
        yield
        clear_request_context()

    def test_concurrent_task_creation_unique_ids(self, temp_dir, mock_config):
        """Concurrent task creation should use unique UUIDs."""
        from src.agents.tools.task_tools import create_agent_task

        num_tasks = 50
        results = []
        lock = threading.Lock()

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):

            def create_task(task_num: int) -> dict[str, Any]:
                result = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "allowed@example.com",
                        "subject": f"Task {task_num}",
                        "body": f"Body {task_num}",
                    },
                    created_by=f"agent_{task_num}",
                )
                with lock:
                    results.append(result)
                return result

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(create_task, i) for i in range(num_tasks)]
                for future in as_completed(futures):
                    future.result()

        # All tasks should succeed
        successes = [r for r in results if r["status"] == "success"]
        assert len(successes) == num_tasks, f"Expected {num_tasks} successes, got {len(successes)}"

        # All task IDs should be unique
        task_ids = [r["task_id"] for r in successes]
        assert len(set(task_ids)) == num_tasks, "Task IDs should be unique"

        # All files should exist and be valid
        input_dir = mock_config.input_dir
        for task_id in task_ids:
            path = input_dir / f"task_{task_id}.json"
            assert path.exists(), f"Missing task file: {path}"
            loaded = read_task_safe(path)
            assert loaded is not None, f"Invalid task file: {path}"
            assert loaded["id"] == task_id

    def test_uuid_collision_handling(self, temp_dir, mock_config):
        """Test behavior when UUID collision occurs (mocked)."""
        from src.agents.tools.task_tools import create_agent_task

        # Use a sequence of UUIDs where first two collide, third is different
        colliding_uuid = "deadbeef1234"
        unique_uuid = "unique5678abcd"

        class MockUUID:
            """Mock UUID that returns colliding values then unique."""

            def __init__(self):
                self.call_count = 0
                self.hex_values = [colliding_uuid, colliding_uuid, unique_uuid]

            @property
            def hex(self):
                idx = min(self.call_count, len(self.hex_values) - 1)
                return self.hex_values[idx]

        mock_uuid_gen = MockUUID()

        def mock_uuid4():
            result = MockUUID()
            result.call_count = mock_uuid_gen.call_count
            mock_uuid_gen.call_count += 1
            return result

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):
            with patch("src.agents.tools.task_tools.uuid.uuid4", side_effect=mock_uuid4):
                # First task should succeed
                result1 = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "allowed@example.com",
                        "subject": "First",
                        "body": "First body",
                    },
                    created_by="agent1",
                )
                assert result1["status"] == "success"
                assert result1["task_id"] == colliding_uuid

                # Second task with same UUID - file already exists
                # Current implementation will overwrite (no collision check)
                result2 = create_agent_task(
                    action="send_email",
                    params={
                        "to_address": "allowed@example.com",
                        "subject": "Second",
                        "body": "Second body",
                    },
                    created_by="agent2",
                )

        # Document current behavior: file is overwritten
        # This test demonstrates the race condition - same UUID = data loss
        assert result2["status"] == "success"
        assert result2["task_id"] == colliding_uuid  # Same ID used

        # Only one file exists (second overwrote first)
        path = mock_config.input_dir / f"task_{colliding_uuid}.json"
        loaded = read_task_safe(path)
        assert loaded is not None
        # Second task overwrote the first
        assert loaded["params"]["subject"] == "Second"

    def test_concurrent_tasks_different_users(self, temp_dir, mock_config):
        """Concurrent tasks from different users should be isolated."""
        from src.agents.tools.task_tools import create_agent_task

        num_users = 5
        tasks_per_user = 10
        results = []
        lock = threading.Lock()

        with patch("src.agents.tools.task_tools.get_config", return_value=mock_config):

            def create_tasks_for_user(user_id: int) -> list[dict[str, Any]]:
                user_results = []
                # Set context for this user (thread-safe context)
                set_request_context(
                    user_email="allowed@example.com",
                    thread_id=f"thread-user-{user_id}",
                    reply_to="allowed@example.com",
                    body=f"User {user_id} body",
                )
                for i in range(tasks_per_user):
                    result = create_agent_task(
                        action="send_email",
                        params={
                            "to_address": "allowed@example.com",
                            "subject": f"User {user_id} Task {i}",
                            "body": f"Body from user {user_id}",
                        },
                        created_by=f"agent_user_{user_id}",
                    )
                    user_results.append((user_id, result))
                with lock:
                    results.extend(user_results)
                return user_results

            with ThreadPoolExecutor(max_workers=num_users) as executor:
                futures = [
                    executor.submit(create_tasks_for_user, i) for i in range(num_users)
                ]
                for future in as_completed(futures):
                    future.result()

        # All tasks should succeed
        total_expected = num_users * tasks_per_user
        successes = [(u, r) for u, r in results if r["status"] == "success"]
        assert len(successes) == total_expected

        # Verify all files exist
        input_dir = mock_config.input_dir
        for user_id, result in successes:
            path = input_dir / f"task_{result['task_id']}.json"
            assert path.exists()


class TestConcurrentReadWrite:
    """Test concurrent read and write operations."""

    def test_reader_writer_stress(self, temp_dir):
        """Stress test with many readers and writers."""
        num_files = 20
        num_writers = 5
        num_readers = 10
        writes_per_writer = 20
        reads_per_reader = 50

        write_counts = {i: 0 for i in range(num_files)}
        read_counts = {i: 0 for i in range(num_files)}
        read_errors = []
        write_lock = threading.Lock()
        read_lock = threading.Lock()
        stop_readers = threading.Event()

        def writer(writer_id: int):
            for _ in range(writes_per_writer):
                file_id = writer_id % num_files
                path = temp_dir / f"file_{file_id}.json"
                task = {
                    "writer": writer_id,
                    "timestamp": time.time(),
                    "data": "x" * 500,
                }
                write_task_atomic(task, path)
                with write_lock:
                    write_counts[file_id] += 1
                time.sleep(0.001)

        def reader(reader_id: int):
            local_reads = 0
            while local_reads < reads_per_reader and not stop_readers.is_set():
                file_id = reader_id % num_files
                path = temp_dir / f"file_{file_id}.json"
                result = read_task_safe(path)
                if result is not None:
                    # Validate data integrity
                    if "writer" not in result or "timestamp" not in result:
                        with read_lock:
                            read_errors.append(
                                {"reader": reader_id, "file": file_id, "data": result}
                            )
                with read_lock:
                    read_counts[file_id] += 1
                    local_reads += 1
                time.sleep(0.001)

        # Start writers first to create files
        writer_threads = [
            threading.Thread(target=writer, args=(i,)) for i in range(num_writers)
        ]
        reader_threads = [
            threading.Thread(target=reader, args=(i,)) for i in range(num_readers)
        ]

        for t in writer_threads:
            t.start()
        time.sleep(0.05)  # Let writers create some files first
        for t in reader_threads:
            t.start()

        for t in writer_threads:
            t.join()
        stop_readers.set()
        for t in reader_threads:
            t.join()

        # No read errors (corrupted data)
        assert len(read_errors) == 0, f"Read errors: {read_errors}"

        # All files should be valid
        for i in range(num_files):
            path = temp_dir / f"file_{i}.json"
            if path.exists():
                loaded = read_task_safe(path)
                if loaded is not None:
                    assert "writer" in loaded
                    assert "timestamp" in loaded

    def test_rapid_overwrite_sequence(self, temp_dir):
        """Test rapid sequential overwrites of same file."""
        path = temp_dir / "rapid.json"
        num_writes = 1000

        # Rapidly overwrite the same file
        for i in range(num_writes):
            task = {"sequence": i, "data": f"iteration_{i}"}
            write_task_atomic(task, path)

        # Final read should return last value
        loaded = read_task_safe(path)
        assert loaded is not None
        assert loaded["sequence"] == num_writes - 1

        # No temp files should remain
        tmp_files = list(temp_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestAtomicityGuarantees:
    """Test atomic file operation guarantees."""

    def test_partial_write_recovery(self, temp_dir):
        """Test that partial writes don't corrupt the file."""
        path = temp_dir / "task.json"

        # Write initial valid data
        initial_task = {"version": 1, "data": "initial"}
        write_task_atomic(initial_task, path)

        # Simulate a write that fails mid-operation
        # atomic_write_json in src.utils uses os.replace
        with patch("src.utils.os.replace") as mock_replace:
            mock_replace.side_effect = OSError("Simulated disk error")
            with pytest.raises(OSError):
                write_task_atomic({"version": 2, "data": "new"}, path)

        # Original file should still be valid
        loaded = read_task_safe(path)
        assert loaded is not None
        assert loaded["version"] == 1
        assert loaded["data"] == "initial"

    def test_temp_file_cleanup_on_error(self, temp_dir):
        """Temp files should be cleaned up on write error."""
        path = temp_dir / "task.json"

        # Force an error during replace
        # atomic_write_json in src.utils uses os.replace
        with patch("src.utils.os.replace") as mock_replace:
            mock_replace.side_effect = OSError("Disk error")
            try:
                write_task_atomic({"data": "test"}, path)
            except OSError:
                pass

        # No temp files should remain
        tmp_files = list(temp_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_task(self, temp_dir):
        """Empty task should be handled correctly."""
        path = temp_dir / "empty.json"
        task = {}
        write_task_atomic(task, path)
        loaded = read_task_safe(path)
        assert loaded == {}

    def test_large_task(self, temp_dir):
        """Large task should be handled correctly."""
        path = temp_dir / "large.json"
        task = {
            "id": "large-task",
            "data": "x" * 1_000_000,  # 1MB of data
            "nested": {"level1": {"level2": {"level3": list(range(1000))}}},
        }
        write_task_atomic(task, path)
        loaded = read_task_safe(path)
        assert loaded == task

    def test_concurrent_large_writes(self, temp_dir):
        """Multiple concurrent large writes should all succeed."""
        num_tasks = 10
        results = []
        lock = threading.Lock()

        def write_large_task(task_id: int) -> bool:
            task = {
                "id": f"large-{task_id}",
                "data": "x" * 100_000,  # 100KB each
            }
            path = temp_dir / f"large_{task_id}.json"
            try:
                write_task_atomic(task, path)
                with lock:
                    results.append((task_id, True))
                return True
            except Exception as e:
                with lock:
                    results.append((task_id, False, str(e)))
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(write_large_task, i) for i in range(num_tasks)]
            for future in as_completed(futures):
                future.result()

        # All should succeed
        successes = [r for r in results if r[1] is True]
        assert len(successes) == num_tasks

        # Verify all files
        for i in range(num_tasks):
            path = temp_dir / f"large_{i}.json"
            loaded = read_task_safe(path)
            assert loaded is not None
            assert loaded["id"] == f"large-{i}"
            assert len(loaded["data"]) == 100_000
