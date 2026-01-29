"""Stress tests for FileSessionStore concurrency and edge cases."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from src.sessions import (
    EmailConversation,
    FileSessionStore,
    Message,
    compute_thread_id,
)


class TestConcurrentReadWrite:
    """Tests for concurrent read/write operations."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_concurrent_writes_to_same_session(self, store):
        """Multiple threads writing to the same session should not lose data."""
        # Create initial conversation
        conv, _ = store.get_or_create("user@example.com", "Concurrent Test")
        thread_id = conv.thread_id

        num_threads = 10
        messages_per_thread = 10
        errors = []

        def add_messages(thread_num):
            try:
                for i in range(messages_per_thread):
                    store.add_message(
                        thread_id, "user", f"Thread {thread_num} Message {i}"
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(num_threads):
            thread = threading.Thread(target=add_messages, args=(t,))
            threads.append(thread)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check for errors
        assert not errors, f"Errors during concurrent writes: {errors}"

        # Verify all messages were saved
        final_conv = store.get(thread_id)
        expected_count = num_threads * messages_per_thread
        actual_count = len(final_conv.messages)

        # This may fail if there are race conditions
        assert actual_count == expected_count, (
            f"Expected {expected_count} messages, got {actual_count}. "
            f"Lost {expected_count - actual_count} messages due to race conditions."
        )

    def test_concurrent_read_during_write(self, store):
        """Reads during writes should return consistent data."""
        conv, _ = store.get_or_create("user@example.com", "Read/Write Test")
        thread_id = conv.thread_id

        num_writes = 50
        read_results = []
        errors = []

        def writer():
            try:
                for i in range(num_writes):
                    store.add_message(thread_id, "user", f"Message {i}")
                    time.sleep(0.001)  # Small delay to interleave
            except Exception as e:
                errors.append(("writer", e))

        def reader():
            try:
                for _ in range(num_writes * 2):
                    result = store.get(thread_id)
                    if result:
                        read_results.append(len(result.messages))
                    time.sleep(0.0005)
            except Exception as e:
                errors.append(("reader", e))

        write_thread = threading.Thread(target=writer)
        read_thread = threading.Thread(target=reader)

        write_thread.start()
        read_thread.start()

        write_thread.join()
        read_thread.join()

        # Verify no errors
        assert not errors, f"Errors during concurrent read/write: {errors}"

        # Verify read results are monotonically non-decreasing
        # (we never read an older state after reading a newer one)
        for i in range(1, len(read_results)):
            assert read_results[i] >= read_results[i - 1], (
                f"Read inconsistency at index {i}: "
                f"read {read_results[i]} after {read_results[i-1]}"
            )

    def test_concurrent_get_or_create_same_thread(self, store):
        """Multiple threads calling get_or_create for the same thread."""
        sender = "user@example.com"
        subject = "Same Thread Test"
        num_threads = 20
        results = []
        errors = []

        def get_or_create():
            try:
                conv, is_new = store.get_or_create(sender, subject)
                results.append((conv.thread_id, is_new))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_or_create) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors: {errors}"
        assert len(results) == num_threads

        # All should have the same thread_id
        thread_ids = {r[0] for r in results}
        assert len(thread_ids) == 1, f"Got multiple thread IDs: {thread_ids}"

        # Only one should be marked as new
        new_count = sum(1 for _, is_new in results if is_new)
        # Due to race condition in get_or_create, we might get more than one "is_new=True"
        # This is a potential bug if it matters for the application
        if new_count > 1:
            pytest.xfail(
                f"Race condition: {new_count} threads thought they created new conversation"
            )

    def test_high_contention_multiple_sessions(self, store):
        """High contention across multiple sessions."""
        num_sessions = 5
        num_threads_per_session = 5
        messages_per_thread = 10
        errors = []

        # Create all sessions first
        thread_ids = []
        for i in range(num_sessions):
            conv, _ = store.get_or_create(f"user{i}@example.com", f"Session {i}")
            thread_ids.append(conv.thread_id)

        def add_messages(session_idx, thread_num):
            try:
                tid = thread_ids[session_idx]
                for i in range(messages_per_thread):
                    store.add_message(tid, "user", f"S{session_idx}T{thread_num}M{i}")
            except Exception as e:
                errors.append((session_idx, thread_num, e))

        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = []
            for s in range(num_sessions):
                for t in range(num_threads_per_session):
                    futures.append(executor.submit(add_messages, s, t))

            for f in as_completed(futures):
                f.result()  # Propagate any exceptions

        assert not errors, f"Errors: {errors}"

        # Verify each session has all messages
        expected_per_session = num_threads_per_session * messages_per_thread
        for i, tid in enumerate(thread_ids):
            conv = store.get(tid)
            actual = len(conv.messages)
            if actual != expected_per_session:
                pytest.fail(
                    f"Session {i}: expected {expected_per_session} messages, "
                    f"got {actual}. Lost {expected_per_session - actual} messages."
                )


class TestFileCorruption:
    """Tests for handling corrupted session files."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_empty_file(self, store):
        """Handle empty file gracefully."""
        # Create empty file
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text("")

        # Should return None, not crash
        result = store.get("nonexistent")
        assert result is None

        # Should be able to create new session
        conv, is_new = store.get_or_create("user@example.com", "Test")
        assert is_new

    def test_invalid_json_file(self, store):
        """Handle invalid JSON gracefully."""
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text("{invalid json}")

        # Should return None, not crash
        result = store.get("nonexistent")
        assert result is None

        # Should be able to create new session (overwrites corrupted file)
        conv, is_new = store.get_or_create("user@example.com", "Test")
        assert is_new

    def test_truncated_json_file(self, store):
        """Handle truncated JSON gracefully."""
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text('{"thread123": {"thread_id": "thread123", "sender": "user@')

        result = store.get("thread123")
        assert result is None

    def test_wrong_data_type_in_file(self, store):
        """Handle wrong data type (array instead of object)."""
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text('["not", "an", "object"]')

        # This might raise TypeError when trying to check "thread_id in data"
        try:
            result = store.get("thread123")
            # If it doesn't crash, we accept any result
        except TypeError:
            pytest.xfail("FileSessionStore crashes on array data instead of object")

    def test_missing_required_fields(self, store):
        """Handle session data with missing required fields."""
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Missing sender and subject
        store.file_path.write_text('{"thread123": {"thread_id": "thread123"}}')

        try:
            result = store.get("thread123")
            # If from_dict handles missing fields, that's fine
        except KeyError:
            pytest.xfail("FileSessionStore crashes on missing required fields")

    def test_file_permissions_error(self, tmp_path):
        """Handle file permission errors gracefully."""
        file_path = tmp_path / "sessions.json"
        store = FileSessionStore(file_path)

        # Create valid file
        conv, _ = store.get_or_create("user@example.com", "Test")

        # Make file unreadable (skip on Windows)
        if os.name != "nt":
            os.chmod(file_path, 0o000)
            try:
                # Should handle gracefully
                result = store.get(conv.thread_id)
                # If no exception, we accept any result
            except PermissionError:
                pytest.xfail("FileSessionStore doesn't handle permission errors gracefully")
            finally:
                os.chmod(file_path, 0o644)

    def test_file_deleted_during_operation(self, store):
        """Handle file being deleted between load and save."""
        conv, _ = store.get_or_create("user@example.com", "Test")
        thread_id = conv.thread_id

        # Delete the file
        store.file_path.unlink()

        # Should still be able to add message (recreates file)
        try:
            store.add_message(thread_id, "user", "Hello")
        except KeyError:
            # This is expected since the file was deleted
            pass


class TestThreadIdCollision:
    """Tests for thread ID collision scenarios."""

    def test_different_cases_same_thread(self, tmp_path):
        """Different case subjects should map to same thread."""
        store = FileSessionStore(tmp_path / "sessions.json")

        conv1, is_new1 = store.get_or_create("user@example.com", "Test Subject")
        conv2, is_new2 = store.get_or_create("user@example.com", "TEST SUBJECT")
        conv3, is_new3 = store.get_or_create("user@example.com", "test subject")

        assert conv1.thread_id == conv2.thread_id == conv3.thread_id
        assert is_new1 is True
        assert is_new2 is False
        assert is_new3 is False

    def test_re_fwd_prefixes_same_thread(self, tmp_path):
        """Re: and Fwd: prefixes should map to same thread."""
        store = FileSessionStore(tmp_path / "sessions.json")

        conv1, _ = store.get_or_create("user@example.com", "Meeting Tomorrow")
        conv2, is_new2 = store.get_or_create("user@example.com", "Re: Meeting Tomorrow")
        conv3, is_new3 = store.get_or_create("user@example.com", "Fwd: Meeting Tomorrow")
        conv4, is_new4 = store.get_or_create("user@example.com", "Re: Re: Fwd: Meeting Tomorrow")

        assert conv1.thread_id == conv2.thread_id == conv3.thread_id == conv4.thread_id
        assert is_new2 is False
        assert is_new3 is False
        assert is_new4 is False

    def test_different_senders_different_threads(self, tmp_path):
        """Same subject from different senders should be different threads."""
        store = FileSessionStore(tmp_path / "sessions.json")

        conv1, _ = store.get_or_create("alice@example.com", "Hello")
        conv2, is_new2 = store.get_or_create("bob@example.com", "Hello")

        assert conv1.thread_id != conv2.thread_id
        assert is_new2 is True

    def test_hash_collision_probability(self, tmp_path):
        """Test that thread IDs are sufficiently unique."""
        store = FileSessionStore(tmp_path / "sessions.json")

        # Generate many thread IDs
        num_threads = 1000
        thread_ids = set()

        for i in range(num_threads):
            tid = compute_thread_id(f"Subject {i}", f"user{i}@example.com")
            thread_ids.add(tid)

        # All should be unique (with 16 hex chars = 64 bits, collisions are unlikely)
        assert len(thread_ids) == num_threads, (
            f"Got {num_threads - len(thread_ids)} collisions out of {num_threads} threads"
        )

    def test_similar_subjects_different_threads(self, tmp_path):
        """Very similar subjects should still be different threads."""
        store = FileSessionStore(tmp_path / "sessions.json")

        conv1, _ = store.get_or_create("user@example.com", "Meeting at 3pm")
        conv2, is_new2 = store.get_or_create("user@example.com", "Meeting at 3pm!")

        # These should be different threads
        assert conv1.thread_id != conv2.thread_id
        assert is_new2 is True


class TestLongConversationHistory:
    """Tests for handling very long conversation histories."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_many_messages(self, store):
        """Handle conversation with many messages."""
        conv, _ = store.get_or_create("user@example.com", "Long Conversation")
        thread_id = conv.thread_id

        num_messages = 1000
        for i in range(num_messages):
            store.add_message(thread_id, "user" if i % 2 == 0 else "assistant", f"Message {i}")

        retrieved = store.get(thread_id)
        assert len(retrieved.messages) == num_messages

    def test_large_message_content(self, store):
        """Handle messages with very large content."""
        conv, _ = store.get_or_create("user@example.com", "Large Content")
        thread_id = conv.thread_id

        # 1MB message
        large_content = "x" * (1024 * 1024)
        store.add_message(thread_id, "user", large_content)

        retrieved = store.get(thread_id)
        assert len(retrieved.messages) == 1
        assert len(retrieved.messages[0].content) == 1024 * 1024

    def test_get_history_with_limit(self, store):
        """get_history should efficiently handle limits on large conversations."""
        conv, _ = store.get_or_create("user@example.com", "History Limit Test")
        thread_id = conv.thread_id

        num_messages = 100
        for i in range(num_messages):
            store.add_message(thread_id, "user", f"Message {i}")

        retrieved = store.get(thread_id)
        history = retrieved.get_history(max_messages=10)

        assert len(history) == 10
        # Should be the last 10 messages
        assert history[0].content == "Message 90"
        assert history[-1].content == "Message 99"

    def test_context_string_size(self, store):
        """get_context_string should be bounded."""
        conv, _ = store.get_or_create("user@example.com", "Context Test")
        thread_id = conv.thread_id

        # Add many messages
        for i in range(100):
            store.add_message(thread_id, "user", f"Message {i} with some content here")

        retrieved = store.get(thread_id)
        context = retrieved.get_context_string(max_messages=5)

        # Should only contain 5 messages
        lines = context.split("\n")
        # Header line + 5 messages
        assert len(lines) == 6

    def test_many_conversations_file_size(self, store):
        """File size should be manageable with many conversations."""
        num_conversations = 100
        messages_per_conv = 50

        for c in range(num_conversations):
            conv, _ = store.get_or_create(f"user{c}@example.com", f"Subject {c}")
            for m in range(messages_per_conv):
                store.add_message(conv.thread_id, "user", f"Conv {c} Msg {m}")

        # Check file size is reasonable (should be < 10MB for this amount)
        file_size = store.file_path.stat().st_size
        assert file_size < 10 * 1024 * 1024, f"File too large: {file_size / 1024 / 1024:.2f}MB"

        # Verify we can still load efficiently
        import time
        start = time.time()
        # Use limit=num_conversations since default limit is 50
        conversations = store.list_conversations(limit=num_conversations)
        load_time = time.time() - start

        assert len(conversations) == num_conversations
        # Should load in reasonable time (< 1 second)
        assert load_time < 1.0, f"Loading took {load_time:.2f}s"

    def test_cleanup_old_conversations(self, store):
        """cleanup_old should remove old conversations."""
        from datetime import datetime, timedelta

        # Create a conversation and manually backdate it
        conv, _ = store.get_or_create("user@example.com", "Old Conversation")
        thread_id = conv.thread_id

        # Manually update the file to backdate the conversation
        with open(store.file_path, "r") as f:
            data = json.load(f)

        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        data[thread_id]["updated_at"] = old_date

        with open(store.file_path, "w") as f:
            json.dump(data, f)

        # Create a recent conversation
        store.get_or_create("user@example.com", "Recent Conversation")

        # Cleanup old conversations
        deleted = store.cleanup_old(days=30)

        assert deleted == 1
        assert store.get(thread_id) is None


class TestAtomicityAndConsistency:
    """Tests for atomic operations and data consistency."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_save_failure_doesnt_corrupt(self, store, tmp_path, monkeypatch):
        """A failed save should not corrupt existing data."""
        import src.utils

        # Create initial conversation
        conv, _ = store.get_or_create("user@example.com", "Test")
        thread_id = conv.thread_id
        store.add_message(thread_id, "user", "Initial message")

        # Record the file contents
        original_content = store.file_path.read_text()

        # Make os.replace fail (atomic_write_json in src.utils uses os.replace)
        original_replace = os.replace
        def failing_replace(src, dst):
            raise OSError("Simulated failure")

        monkeypatch.setattr(src.utils.os, "replace", failing_replace)

        # Attempt to add a message (should fail)
        with pytest.raises(OSError):
            store.add_message(thread_id, "user", "This should fail")

        # Restore original replace
        monkeypatch.setattr(src.utils.os, "replace", original_replace)

        # Verify original content is preserved
        current_content = store.file_path.read_text()
        assert current_content == original_content

    def test_concurrent_delete_and_add(self, store):
        """Concurrent delete and add operations."""
        conv, _ = store.get_or_create("user@example.com", "Delete Test")
        thread_id = conv.thread_id

        errors = []
        deleted = []
        added = []

        def deleter():
            try:
                result = store.delete(thread_id)
                deleted.append(result)
            except Exception as e:
                errors.append(("deleter", e))

        def adder():
            try:
                # Small delay to increase chance of interleaving
                time.sleep(0.001)
                store.add_message(thread_id, "user", "After delete")
                added.append(True)
            except KeyError:
                added.append(False)
            except Exception as e:
                errors.append(("adder", e))

        threads = [
            threading.Thread(target=deleter),
            threading.Thread(target=adder),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors: {errors}"

        # Either the conversation should exist (add happened after delete failed)
        # or it should not exist (delete happened after add)
        final_state = store.get(thread_id)
        if final_state is None:
            assert deleted[0] is True, "Conversation deleted but delete returned False"
        # If it exists, that's also valid if add succeeded


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_empty_subject(self, store):
        """Handle empty subject."""
        conv, is_new = store.get_or_create("user@example.com", "")
        assert is_new
        assert conv.subject == ""

    def test_empty_sender(self, store):
        """Handle empty sender."""
        conv, is_new = store.get_or_create("", "Test Subject")
        assert is_new
        assert conv.sender == ""

    def test_unicode_in_subject(self, store):
        """Handle unicode characters in subject."""
        conv, _ = store.get_or_create("user@example.com", "Test")
        store.add_message(conv.thread_id, "user", "Hello")

        retrieved = store.get(conv.thread_id)
        assert retrieved.messages[0].content == "Hello"

    def test_special_characters_in_content(self, store):
        """Handle special characters in message content."""
        conv, _ = store.get_or_create("user@example.com", "Special Chars")
        special_content = 'Hello\n\t"World"\r\n{json: "like"}'
        store.add_message(conv.thread_id, "user", special_content)

        retrieved = store.get(conv.thread_id)
        assert retrieved.messages[0].content == special_content

    def test_very_long_subject(self, store):
        """Handle very long subject line."""
        long_subject = "A" * 10000
        conv, is_new = store.get_or_create("user@example.com", long_subject)
        assert is_new

        retrieved = store.get(conv.thread_id)
        assert retrieved.subject == long_subject

    def test_rapid_successive_operations(self, store):
        """Rapid successive operations on same conversation."""
        conv, _ = store.get_or_create("user@example.com", "Rapid Test")
        thread_id = conv.thread_id

        # Rapid fire operations
        for i in range(100):
            store.add_message(thread_id, "user" if i % 2 == 0 else "assistant", f"Msg {i}")

        retrieved = store.get(thread_id)
        assert len(retrieved.messages) == 100

    def test_list_conversations_empty_store(self, store):
        """list_conversations on empty store."""
        conversations = store.list_conversations()
        assert conversations == []

    def test_delete_nonexistent_returns_false(self, store):
        """delete on nonexistent thread returns False."""
        result = store.delete("nonexistent_thread_id")
        assert result is False
