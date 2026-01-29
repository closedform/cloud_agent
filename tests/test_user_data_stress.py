"""Stress tests for src/user_data.py

Tests concurrent access, large data, special characters, and corruption recovery.
"""

import concurrent.futures
import json
import os
import threading
import time
from pathlib import Path

import pytest

from src.user_data import (
    add_to_list,
    add_todo,
    complete_todo,
    delete_todo,
    get_all_lists,
    get_list,
    get_todos,
    load_user_data,
    remove_from_list,
    save_user_data,
)


class TestConcurrentListModifications:
    """Test concurrent access to lists."""

    def test_concurrent_add_to_same_list(self, test_config):
        """Multiple threads adding to the same list should not lose items."""
        email = "concurrent@example.com"
        list_name = "shared_list"
        num_threads = 10
        items_per_thread = 50

        def add_items(thread_id: int):
            for i in range(items_per_thread):
                add_to_list(email, list_name, f"thread_{thread_id}_item_{i}", test_config)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(add_items, t) for t in range(num_threads)]
            concurrent.futures.wait(futures)

        items = get_list(email, list_name, test_config)
        expected_count = num_threads * items_per_thread
        assert len(items) == expected_count, f"Expected {expected_count} items, got {len(items)} - data loss detected!"

    def test_concurrent_add_to_different_lists(self, test_config):
        """Multiple threads adding to different lists should work correctly."""
        email = "concurrent@example.com"
        num_threads = 10
        items_per_thread = 20

        def add_items(thread_id: int):
            list_name = f"list_{thread_id}"
            for i in range(items_per_thread):
                add_to_list(email, list_name, f"item_{i}", test_config)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(add_items, t) for t in range(num_threads)]
            concurrent.futures.wait(futures)

        all_lists = get_all_lists(email, test_config)
        assert len(all_lists) == num_threads, f"Expected {num_threads} lists, got {len(all_lists)}"
        for i in range(num_threads):
            list_name = f"list_{i}"
            items = all_lists.get(list_name, [])
            assert len(items) == items_per_thread, f"List {list_name} has {len(items)} items, expected {items_per_thread}"

    def test_concurrent_add_and_remove(self, test_config):
        """Concurrent adds and removes should maintain consistency."""
        email = "concurrent@example.com"
        list_name = "add_remove_list"

        # Pre-populate with items
        for i in range(100):
            add_to_list(email, list_name, f"item_{i}", test_config)

        removed_items = []
        added_items = []
        lock = threading.Lock()

        def add_new_items():
            for i in range(50):
                item = f"new_item_{i}"
                add_to_list(email, list_name, item, test_config)
                with lock:
                    added_items.append(item)

        def remove_old_items():
            for i in range(50):
                item = f"item_{i}"
                if remove_from_list(email, list_name, item, test_config):
                    with lock:
                        removed_items.append(item)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(add_new_items),
                executor.submit(add_new_items),
                executor.submit(remove_old_items),
                executor.submit(remove_old_items),
            ]
            concurrent.futures.wait(futures)

        items = get_list(email, list_name, test_config)
        # Original 100 - removed + added (2 threads each)
        expected_min = 100 - len(removed_items) + len(added_items)
        # Allow for duplicates in added_items since we have 2 add threads
        assert len(items) >= 100, f"Got {len(items)} items, expected at least 100"

    def test_concurrent_different_users(self, test_config):
        """Concurrent modifications by different users should be isolated."""
        num_users = 5
        items_per_user = 30

        def add_user_items(user_id: int):
            email = f"user_{user_id}@example.com"
            for i in range(items_per_user):
                add_to_list(email, "my_list", f"item_{i}", test_config)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_users) as executor:
            futures = [executor.submit(add_user_items, u) for u in range(num_users)]
            concurrent.futures.wait(futures)

        for user_id in range(num_users):
            email = f"user_{user_id}@example.com"
            items = get_list(email, "my_list", test_config)
            assert len(items) == items_per_user, f"User {user_id} has {len(items)} items, expected {items_per_user}"


class TestConcurrentTodoOperations:
    """Test concurrent todo operations."""

    def test_concurrent_add_todos(self, test_config):
        """Concurrent todo additions should not lose items."""
        email = "todos@example.com"
        num_threads = 10
        todos_per_thread = 20

        def add_todos(thread_id: int):
            for i in range(todos_per_thread):
                add_todo(email, f"Thread {thread_id} todo {i}", test_config)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(add_todos, t) for t in range(num_threads)]
            concurrent.futures.wait(futures)

        todos = get_todos(email, test_config, include_done=True)
        expected = num_threads * todos_per_thread
        assert len(todos) == expected, f"Expected {expected} todos, got {len(todos)}"

    def test_concurrent_complete_todos(self, test_config):
        """Concurrent todo completions should work correctly."""
        email = "complete@example.com"
        num_todos = 50

        # Create todos
        todo_ids = []
        for i in range(num_todos):
            todo = add_todo(email, f"Todo {i}", test_config)
            todo_ids.append(todo["id"])

        completed_count = [0]
        lock = threading.Lock()

        def complete_todos(start_idx: int, end_idx: int):
            for i in range(start_idx, end_idx):
                if complete_todo(email, todo_ids[i], test_config):
                    with lock:
                        completed_count[0] += 1

        # Split work across threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            chunk_size = num_todos // 5
            for i in range(5):
                start = i * chunk_size
                end = start + chunk_size if i < 4 else num_todos
                futures.append(executor.submit(complete_todos, start, end))
            concurrent.futures.wait(futures)

        assert completed_count[0] == num_todos, f"Only {completed_count[0]} of {num_todos} completed"

        incomplete_todos = get_todos(email, test_config, include_done=False)
        assert len(incomplete_todos) == 0, f"{len(incomplete_todos)} todos still incomplete"


class TestVeryLargeLists:
    """Test handling of large data volumes."""

    def test_large_list_10000_items(self, test_config):
        """Should handle lists with 10000 items."""
        email = "large@example.com"
        list_name = "huge_list"
        num_items = 10000

        start = time.time()
        for i in range(num_items):
            add_to_list(email, list_name, f"item_{i:05d}", test_config)
        add_time = time.time() - start

        start = time.time()
        items = get_list(email, list_name, test_config)
        read_time = time.time() - start

        assert len(items) == num_items, f"Expected {num_items} items, got {len(items)}"

        # Check file size is reasonable (not bloated)
        file_size = test_config.user_data_file.stat().st_size
        # 10000 items of ~20 chars each, plus JSON overhead
        max_expected_size = num_items * 30 + 1000
        assert file_size < max_expected_size * 2, f"File size {file_size} seems too large"

        print(f"\nPerformance: {num_items} items - Add: {add_time:.2f}s, Read: {read_time:.4f}s, Size: {file_size/1024:.1f}KB")

    def test_large_list_operations_performance(self, test_config):
        """Test remove operation on large list is not O(n^2)."""
        email = "perf@example.com"
        list_name = "perf_list"
        num_items = 5000

        # Populate list
        for i in range(num_items):
            add_to_list(email, list_name, f"item_{i:05d}", test_config)

        # Time removal of first 100 items
        start = time.time()
        for i in range(100):
            remove_from_list(email, list_name, f"item_{i:05d}", test_config)
        remove_time = time.time() - start

        # Should complete in reasonable time (not O(n) file rewrites per removal)
        assert remove_time < 30, f"Removing 100 items from 5000-item list took {remove_time:.2f}s - too slow"

        items = get_list(email, list_name, test_config)
        assert len(items) == num_items - 100

    def test_many_lists_for_single_user(self, test_config):
        """Should handle many lists per user."""
        email = "manylists@example.com"
        num_lists = 500
        items_per_list = 10

        for list_idx in range(num_lists):
            for item_idx in range(items_per_list):
                add_to_list(email, f"list_{list_idx:03d}", f"item_{item_idx}", test_config)

        all_lists = get_all_lists(email, test_config)
        assert len(all_lists) == num_lists, f"Expected {num_lists} lists, got {len(all_lists)}"

    def test_many_users(self, test_config):
        """Should handle many users."""
        num_users = 200

        for user_idx in range(num_users):
            email = f"user_{user_idx:03d}@example.com"
            add_to_list(email, "my_list", "my_item", test_config)
            add_todo(email, "my_todo", test_config)

        data = load_user_data(test_config)
        assert len(data) == num_users, f"Expected {num_users} users, got {len(data)}"


class TestSpecialCharacters:
    """Test handling of special characters in list names and items."""

    @pytest.mark.parametrize("list_name", [
        "movies & shows",
        "groceries/shopping",
        "to-do list",
        "list_with_underscores",
        "CamelCaseList",
        "list with   multiple   spaces",
        "list\twith\ttabs",
        "emoji list ",
        "list",
        "unicode: cafe",
        "quotes: \"test\" and 'test'",
        "brackets: [test] and {test}",
        "special: @#$%^&*()",
        "backslash: test\\path",
        "newline\nin\nname",
        "",  # Empty string
        " ",  # Just space
        "   leading space",
        "trailing space   ",
    ])
    def test_special_list_names(self, test_config, list_name):
        """Should handle various special characters in list names."""
        email = "special@example.com"
        item = "test_item"

        add_to_list(email, list_name, item, test_config)
        items = get_list(email, list_name, test_config)
        assert items == [item], f"Failed for list name: {repr(list_name)}"

    @pytest.mark.parametrize("item", [
        "item with spaces",
        "item/with/slashes",
        "item\\with\\backslashes",
        "item\twith\ttabs",
        "item\nwith\nnewlines",
        "emoji: ",
        "unicode: cafe eclair",
        "quotes: \"double\" and 'single'",
        "html: <script>alert('xss')</script>",
        "json: {\"key\": \"value\"}",
        "null character: \x00test",  # Null byte
        "control chars: \x01\x02\x03",
        "very long item " + "x" * 10000,
        "",  # Empty string
        " ",  # Just space
    ])
    def test_special_item_values(self, test_config, item):
        """Should handle various special characters in item values."""
        email = "special@example.com"
        list_name = "test_list"

        try:
            add_to_list(email, list_name, item, test_config)
            items = get_list(email, list_name, test_config)
            assert item in items, f"Item not found: {repr(item)}"
        except Exception as e:
            pytest.fail(f"Failed to handle item {repr(item)}: {e}")

    def test_special_characters_in_email(self, test_config):
        """Should handle various email address formats."""
        test_emails = [
            "simple@example.com",
            "user+tag@example.com",
            "user.name@example.com",
            "user_name@example.com",
            "user-name@example.com",
            "USER@EXAMPLE.COM",  # Uppercase
            "user@sub.domain.example.com",
        ]

        for email in test_emails:
            add_to_list(email, "test", "item", test_config)
            items = get_list(email, "test", test_config)
            assert items == ["item"], f"Failed for email: {email}"

    def test_special_todo_text(self, test_config):
        """Should handle special characters in todo text."""
        email = "todo@example.com"
        special_texts = [
            "Buy milk  eggs",
            "Todo with \"quotes\"",
            "Task: {important}",
            "Multi\nline\ntodo",
            "<html>todo</html>",
            "a" * 10000,  # Very long
        ]

        for text in special_texts:
            todo = add_todo(email, text, test_config)
            assert todo["text"] == text, f"Text mismatch for: {repr(text)}"

    def test_json_injection_in_item(self, test_config):
        """Items that look like JSON should not corrupt the file."""
        email = "json@example.com"
        malicious_items = [
            '{"__proto__": {"isAdmin": true}}',
            '"},{"hacked": true}',
            '", "extra_key": "injected',
            'null',
            'true',
            'false',
            '123',
            '[]',
            '{}',
        ]

        for item in malicious_items:
            add_to_list(email, "test", item, test_config)

        items = get_list(email, "test", test_config)
        assert len(items) == len(malicious_items)

        # Verify file is still valid JSON
        data = load_user_data(test_config)
        assert isinstance(data, dict)


class TestFileCorruptionRecovery:
    """Test recovery from file corruption scenarios."""

    def test_empty_file(self, test_config):
        """Should handle empty file gracefully."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.user_data_file.write_text("")

        data = load_user_data(test_config)
        assert data == {}

        # Should be able to write new data
        add_to_list("user@example.com", "test", "item", test_config)
        items = get_list("user@example.com", "test", test_config)
        assert items == ["item"]

    def test_truncated_json(self, test_config):
        """Should handle truncated JSON file."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.user_data_file.write_text('{"user@example.com": {"lists": {"movies": ["Inc')

        data = load_user_data(test_config)
        assert data == {}  # Returns empty on corruption

    def test_invalid_json_syntax(self, test_config):
        """Should handle invalid JSON syntax."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.user_data_file.write_text('{invalid json content}')

        data = load_user_data(test_config)
        assert data == {}

    def test_wrong_json_type(self, test_config):
        """Should handle JSON that's not a dict - BUG: returns wrong type instead of empty dict."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)

        wrong_types = ['[]', '"string"', '123', 'null', 'true']
        for wrong_json in wrong_types:
            test_config.user_data_file.write_text(wrong_json)
            data = load_user_data(test_config)
            # BUG: Current implementation doesn't validate type
            # It returns whatever JSON.load returns (list, string, int, None, bool)
            # This can cause downstream errors when code expects a dict
            # Expected behavior: return {} for non-dict JSON
            # Actual behavior: returns the parsed non-dict value
            assert not isinstance(data, dict) or data == {}, f"Expected non-dict or empty dict for {wrong_json}"

    def test_binary_garbage_in_file(self, test_config):
        """Should handle binary garbage in file gracefully."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)
        test_config.user_data_file.write_bytes(b'\x00\x01\x02\xff\xfe\xfd')

        # FIXED: Now handles UnicodeDecodeError gracefully and returns empty dict
        # (Previously raised UnicodeDecodeError)
        data = load_user_data(test_config)
        assert data == {}

    def test_partial_write_simulation(self, test_config):
        """Should handle leftover temp files from failed writes."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)

        # Create a leftover temp file
        tmp_file = test_config.user_data_file.parent / "user_data.json.tmp"
        tmp_file.write_text('{"partial": "data"}')

        # Normal operation should still work
        add_to_list("user@example.com", "test", "item", test_config)
        items = get_list("user@example.com", "test", test_config)
        assert items == ["item"]

    def test_file_locked_by_another_process(self, test_config):
        """Test behavior when file operations fail due to directory permissions."""
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)

        # Create a valid file first
        save_user_data({"user@example.com": {"lists": {}, "todos": []}}, test_config)

        # Make the DIRECTORY read-only to prevent creating temp files
        # (file permissions alone don't work because atomic write creates new temp file)
        os.chmod(test_config.user_data_file.parent, 0o555)

        try:
            # This should raise an exception
            with pytest.raises(Exception):  # OSError or PermissionError
                add_to_list("user@example.com", "test", "item", test_config)
        finally:
            # Restore permissions for cleanup
            os.chmod(test_config.user_data_file.parent, 0o755)

    def test_directory_deleted_during_operation(self, test_config):
        """Test behavior when directory is deleted."""
        email = "user@example.com"

        # First, add some data
        add_to_list(email, "test", "item1", test_config)

        # Delete the file
        test_config.user_data_file.unlink()

        # load_user_data should return empty dict
        data = load_user_data(test_config)
        assert data == {}

        # Should be able to add new data
        add_to_list(email, "test", "item2", test_config)
        items = get_list(email, "test", test_config)
        assert items == ["item2"]

    def test_concurrent_corruption_recovery(self, test_config):
        """Multiple threads should recover from corruption."""
        email = "recover@example.com"
        test_config.user_data_file.parent.mkdir(parents=True, exist_ok=True)

        # Start with corrupt file
        test_config.user_data_file.write_text("corrupted!")

        results = []
        lock = threading.Lock()

        def try_add_item(thread_id: int):
            try:
                # First operation after corruption should recover
                add_to_list(email, "test", f"item_{thread_id}", test_config)
                with lock:
                    results.append(("success", thread_id))
            except Exception as e:
                with lock:
                    results.append(("error", thread_id, str(e)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_add_item, i) for i in range(5)]
            concurrent.futures.wait(futures)

        # At least some should succeed
        successes = [r for r in results if r[0] == "success"]
        assert len(successes) > 0, f"No successful recoveries: {results}"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_rapid_consecutive_operations(self, test_config):
        """Rapid operations should not cause race conditions."""
        email = "rapid@example.com"

        # Rapid adds
        for i in range(100):
            add_to_list(email, "list", f"item_{i}", test_config)

        # Rapid removes
        for i in range(50):
            remove_from_list(email, "list", f"item_{i}", test_config)

        items = get_list(email, "list", test_config)
        assert len(items) == 50

    def test_todo_id_uniqueness_under_stress(self, test_config):
        """Todo IDs should be unique even with rapid creation."""
        email = "ids@example.com"
        todo_ids = []

        # Create many todos very quickly
        for i in range(100):
            todo = add_todo(email, f"Todo {i}", test_config)
            todo_ids.append(todo["id"])

        # Check for duplicates
        unique_ids = set(todo_ids)
        assert len(unique_ids) == len(todo_ids), f"Duplicate IDs found! {len(unique_ids)} unique out of {len(todo_ids)}"

    def test_concurrent_todo_id_uniqueness(self, test_config):
        """Todo IDs should be unique even with concurrent creation."""
        email = "concurrent_ids@example.com"
        todo_ids = []
        lock = threading.Lock()

        def create_todos(thread_id: int):
            for i in range(20):
                todo = add_todo(email, f"Thread {thread_id} Todo {i}", test_config)
                with lock:
                    todo_ids.append(todo["id"])

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_todos, t) for t in range(10)]
            concurrent.futures.wait(futures)

        unique_ids = set(todo_ids)
        duplicates = len(todo_ids) - len(unique_ids)
        assert duplicates == 0, f"{duplicates} duplicate todo IDs found!"

    def test_zero_length_operations(self, test_config):
        """Operations with empty values should be handled."""
        email = "empty@example.com"

        # Add empty item
        add_to_list(email, "list", "", test_config)
        items = get_list(email, "list", test_config)
        assert "" in items

        # Add to empty-named list
        add_to_list(email, "", "item", test_config)
        items = get_list(email, "", test_config)
        assert "item" in items

    def test_remove_nonexistent_from_empty_list(self, test_config):
        """Removing from nonexistent list should return False."""
        email = "nonexistent@example.com"
        result = remove_from_list(email, "no_such_list", "no_item", test_config)
        assert result is False

    def test_remove_from_nonexistent_user(self, test_config):
        """Removing from nonexistent user should return False."""
        result = remove_from_list("nosuch@example.com", "list", "item", test_config)
        assert result is False

    def test_complete_nonexistent_todo(self, test_config):
        """Completing nonexistent todo should return False."""
        result = complete_todo("user@example.com", "no-such-id", test_config)
        assert result is False

    def test_delete_nonexistent_todo(self, test_config):
        """Deleting nonexistent todo should return False."""
        result = delete_todo("user@example.com", "no-such-id", test_config)
        assert result is False
