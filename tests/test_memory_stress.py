"""Stress tests for the memory module.

Tests edge cases including:
- Very long facts (10000 chars)
- Special characters in facts/categories/tags
- Concurrent memory operations
- Memory file corruption recovery
"""

import concurrent.futures
import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.memory import (
    Fact,
    add_fact,
    delete_fact,
    get_all_facts,
    get_facts_by_category,
    search_facts,
    update_fact,
    _get_memory_file,
    _load_user_memory,
    _save_user_memory,
    _memory_lock,
)


@pytest.fixture
def test_email():
    return "stress_test@example.com"


@pytest.fixture
def memory_setup(test_config, test_email):
    """Set up memory directory and clean up after tests."""
    with patch("src.memory.get_config", return_value=test_config):
        memory_file = _get_memory_file(test_email)
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        # Clean up any existing test data
        if memory_file.exists():
            memory_file.unlink()
        yield memory_file
        # Cleanup after test
        if memory_file.exists():
            memory_file.unlink()


class TestVeryLongFacts:
    """Tests for handling very long fact content."""

    def test_add_10000_char_fact(self, test_config, test_email, memory_setup):
        """Test adding a fact with 10000 characters."""
        with patch("src.memory.get_config", return_value=test_config):
            long_content = "A" * 10000
            fact = add_fact(
                email=test_email,
                content=long_content,
                category="test",
            )

            assert len(fact.content) == 10000

            # Verify persistence
            facts = get_all_facts(test_email)
            assert len(facts) == 1
            assert len(facts[0].content) == 10000

    def test_add_very_long_source_context(self, test_config, test_email, memory_setup):
        """Test adding a fact with very long source context."""
        with patch("src.memory.get_config", return_value=test_config):
            long_context = "B" * 10000
            fact = add_fact(
                email=test_email,
                content="Test fact",
                category="test",
                source_context=long_context,
            )

            assert len(fact.source_context) == 10000
            facts = get_all_facts(test_email)
            assert len(facts[0].source_context) == 10000

    def test_add_many_long_keywords(self, test_config, test_email, memory_setup):
        """Test adding a fact with many long keywords."""
        with patch("src.memory.get_config", return_value=test_config):
            # 100 keywords, each 100 chars
            keywords = ["K" * 100 for _ in range(100)]
            fact = add_fact(
                email=test_email,
                content="Test fact",
                category="test",
                keywords=keywords,
            )

            assert len(fact.keywords) == 100
            assert all(len(kw) == 100 for kw in fact.keywords)

    def test_search_long_content(self, test_config, test_email, memory_setup):
        """Test searching within long content."""
        with patch("src.memory.get_config", return_value=test_config):
            # Create content with searchable needle in the middle
            long_content = "A" * 5000 + "NEEDLE" + "B" * 4994
            add_fact(
                email=test_email,
                content=long_content,
                category="test",
            )

            results = search_facts(test_email, "NEEDLE")
            assert len(results) == 1
            assert "NEEDLE" in results[0].content


class TestSpecialCharacters:
    """Tests for special characters in facts, categories, and tags."""

    def test_unicode_in_content(self, test_config, test_email, memory_setup):
        """Test Unicode characters in fact content."""
        with patch("src.memory.get_config", return_value=test_config):
            # Use actual unicode chars, not surrogate pairs
            content = "Has cat named \u732b (neko) \U0001f431 with emoji \u2764\ufe0f"
            fact = add_fact(
                email=test_email,
                content=content,
                category="pets",
            )

            facts = get_all_facts(test_email)
            assert facts[0].content == content

    def test_unicode_in_category(self, test_config, test_email, memory_setup):
        """Test Unicode characters in category."""
        with patch("src.memory.get_config", return_value=test_config):
            category = "\u30da\u30c3\u30c8\U0001f436"  # Japanese "pet" + dog emoji
            fact = add_fact(
                email=test_email,
                content="Has a dog",
                category=category,
            )

            facts = get_facts_by_category(test_email, category)
            assert len(facts) == 1

    def test_unicode_in_keywords(self, test_config, test_email, memory_setup):
        """Test Unicode characters in keywords."""
        with patch("src.memory.get_config", return_value=test_config):
            keywords = ["\u732b", "\u72ac", "\U0001f431", "\u5bfe\u8c61"]
            fact = add_fact(
                email=test_email,
                content="Has pets",
                category="pets",
                keywords=keywords,
            )

            results = search_facts(test_email, "\u732b")
            assert len(results) == 1

    def test_json_special_chars_in_content(self, test_config, test_email, memory_setup):
        """Test JSON special characters in fact content."""
        with patch("src.memory.get_config", return_value=test_config):
            # Characters that need escaping in JSON
            content = 'Has quote "test" and backslash \\ and newline \n and tab \t'
            fact = add_fact(
                email=test_email,
                content=content,
                category="test",
            )

            facts = get_all_facts(test_email)
            assert facts[0].content == content

    def test_null_bytes_in_content(self, test_config, test_email, memory_setup):
        """Test null bytes in content (potential security issue)."""
        with patch("src.memory.get_config", return_value=test_config):
            # Null bytes can cause issues in string handling
            content = "Has \x00 null byte"
            fact = add_fact(
                email=test_email,
                content=content,
                category="test",
            )

            facts = get_all_facts(test_email)
            assert "\x00" in facts[0].content

    def test_path_traversal_in_email(self, test_config, test_email, memory_setup):
        """Test path traversal attempts in email are sanitized."""
        with patch("src.memory.get_config", return_value=test_config):
            malicious_email = "../../../etc/passwd@evil.com"
            memory_file = _get_memory_file(malicious_email)

            # Should be in the memory directory, not traversing up
            assert "memory" in str(memory_file)
            # Should not contain ".." in the final path component
            assert ".." not in memory_file.name

    def test_newlines_in_category(self, test_config, test_email, memory_setup):
        """Test newline characters in category."""
        with patch("src.memory.get_config", return_value=test_config):
            category = "pets\nwith\nnewlines"
            fact = add_fact(
                email=test_email,
                content="Has a pet",
                category=category,
            )

            # Category should be stored as-is
            facts = get_all_facts(test_email)
            assert facts[0].category == category

    def test_empty_strings(self, test_config, test_email, memory_setup):
        """Test empty strings in various fields.

        Empty content is now rejected with ValueError to prevent storing
        useless facts. Empty category is still allowed.
        """
        import pytest

        with patch("src.memory.get_config", return_value=test_config):
            # Empty content should raise ValueError
            with pytest.raises(ValueError, match="empty or whitespace"):
                add_fact(
                    email=test_email,
                    content="",  # Empty content - now rejected
                    category="",
                    source_context="",
                    keywords=[],
                )

            # Empty category with valid content should work
            fact = add_fact(
                email=test_email,
                content="Valid content",
                category="",  # Empty category is allowed
                source_context="",
                keywords=[],
            )

            facts = get_all_facts(test_email)
            assert len(facts) == 1
            assert facts[0].content == "Valid content"
            assert facts[0].category == ""

    def test_whitespace_only_content(self, test_config, test_email, memory_setup):
        """Test whitespace-only content.

        Whitespace-only content is now rejected with ValueError since it
        provides no meaningful information.
        """
        import pytest

        with patch("src.memory.get_config", return_value=test_config):
            content = "   \t\n  "
            with pytest.raises(ValueError, match="empty or whitespace"):
                add_fact(
                    email=test_email,
                    content=content,
                    category="test",
                )


class TestConcurrentOperations:
    """Tests for concurrent memory operations."""

    def test_concurrent_adds_same_user(self, test_config, test_email, memory_setup):
        """Test concurrent adds for the same user."""
        with patch("src.memory.get_config", return_value=test_config):
            num_threads = 10
            facts_per_thread = 10
            results = []
            errors = []

            def add_facts(thread_id):
                try:
                    for i in range(facts_per_thread):
                        fact = add_fact(
                            email=test_email,
                            content=f"Fact from thread {thread_id}, iteration {i}",
                            category=f"thread_{thread_id}",
                        )
                        results.append(fact)
                except Exception as e:
                    errors.append(e)

            threads = []
            for i in range(num_threads):
                t = threading.Thread(target=add_facts, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Check no errors
            assert len(errors) == 0, f"Errors occurred: {errors}"

            # All facts should be persisted
            facts = get_all_facts(test_email)
            expected_count = num_threads * facts_per_thread
            assert len(facts) == expected_count, f"Expected {expected_count}, got {len(facts)}"

    def test_concurrent_adds_different_users(self, test_config, memory_setup):
        """Test concurrent adds for different users."""
        with patch("src.memory.get_config", return_value=test_config):
            num_users = 5
            facts_per_user = 10
            errors = []

            def add_facts_for_user(user_id):
                try:
                    email = f"user{user_id}@example.com"
                    for i in range(facts_per_user):
                        add_fact(
                            email=email,
                            content=f"Fact {i} for user {user_id}",
                            category="test",
                        )
                except Exception as e:
                    errors.append(e)

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_users) as executor:
                futures = [executor.submit(add_facts_for_user, i) for i in range(num_users)]
                concurrent.futures.wait(futures)

            assert len(errors) == 0, f"Errors occurred: {errors}"

            # Verify each user has correct number of facts
            for user_id in range(num_users):
                email = f"user{user_id}@example.com"
                facts = get_all_facts(email)
                assert len(facts) == facts_per_user

    def test_concurrent_read_write(self, test_config, test_email, memory_setup):
        """Test concurrent reads and writes."""
        with patch("src.memory.get_config", return_value=test_config):
            # Pre-populate with some facts
            for i in range(5):
                add_fact(test_email, f"Initial fact {i}", "initial")

            read_results = []
            write_results = []
            errors = []

            def reader():
                try:
                    for _ in range(10):
                        facts = get_all_facts(test_email)
                        read_results.append(len(facts))
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(("reader", e))

            def writer():
                try:
                    for i in range(10):
                        fact = add_fact(test_email, f"New fact {i}", "new")
                        write_results.append(fact.id)
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(("writer", e))

            threads = [
                threading.Thread(target=reader),
                threading.Thread(target=reader),
                threading.Thread(target=writer),
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Errors occurred: {errors}"

            # Final count should be 5 initial + 10 new = 15
            facts = get_all_facts(test_email)
            assert len(facts) == 15

    def test_concurrent_delete_and_add(self, test_config, test_email, memory_setup):
        """Test concurrent deletes and adds."""
        with patch("src.memory.get_config", return_value=test_config):
            # Pre-populate
            initial_facts = []
            for i in range(10):
                fact = add_fact(test_email, f"Initial fact {i}", "initial")
                initial_facts.append(fact)

            errors = []

            def deleter():
                try:
                    for fact in initial_facts[:5]:
                        delete_fact(test_email, fact.id)
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(("deleter", e))

            def adder():
                try:
                    for i in range(5):
                        add_fact(test_email, f"New fact {i}", "new")
                        time.sleep(0.01)
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

            assert len(errors) == 0, f"Errors occurred: {errors}"

            # Should have 10 - 5 + 5 = 10 facts
            facts = get_all_facts(test_email)
            assert len(facts) == 10


class TestFileCorruptionRecovery:
    """Tests for handling corrupted memory files."""

    def test_empty_file_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from empty file."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file
            memory_file.write_text("")

            # Should return empty list, not error
            facts = get_all_facts(test_email)
            assert facts == []

            # Should be able to add new facts
            add_fact(test_email, "New fact", "test")
            facts = get_all_facts(test_email)
            assert len(facts) == 1

    def test_invalid_json_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from invalid JSON."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Write invalid JSON
            memory_file.write_text("{invalid json content")

            # Should return empty list, not error
            facts = get_all_facts(test_email)
            assert facts == []

    def test_truncated_json_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from truncated JSON."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Write truncated JSON (simulating crash during write)
            memory_file.write_text('[{"id": "fact_1", "content": "test", "category": "t')

            facts = get_all_facts(test_email)
            assert facts == []

    def test_missing_required_field_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from JSON with missing required fields."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON missing required 'id' field
            invalid_data = [{"content": "test", "category": "test", "created_at": "2024-01-01"}]
            memory_file.write_text(json.dumps(invalid_data))

            # Should return empty list due to KeyError
            facts = get_all_facts(test_email)
            assert facts == []

    def test_wrong_type_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from JSON with wrong type (not array)."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON object instead of array
            memory_file.write_text('{"single": "object"}')

            # Should raise an error or return empty (depends on implementation)
            # The current implementation will fail on iteration
            try:
                facts = get_all_facts(test_email)
                # If it doesn't error, check behavior
            except TypeError:
                pass  # Expected behavior if not handled

    def test_binary_file_recovery(self, test_config, test_email, memory_setup):
        """Test recovery from binary garbage in file.

        BUG FIXED: Binary garbage now gracefully returns empty list.
        The _load_user_memory function now catches UnicodeDecodeError along
        with other corruption-related exceptions.
        """
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            # Write binary garbage
            memory_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")

            # Now gracefully returns empty list instead of raising
            facts = get_all_facts(test_email)
            assert facts == []

    def test_permission_denied_read(self, test_config, test_email, memory_setup):
        """Test handling of permission denied on read."""
        with patch("src.memory.get_config", return_value=test_config):
            memory_file = _get_memory_file(test_email)
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            memory_file.write_text("[]")

            # Make file unreadable
            original_mode = memory_file.stat().st_mode
            try:
                os.chmod(memory_file, 0o000)
                # Should handle permission error gracefully
                try:
                    facts = get_all_facts(test_email)
                    # If it succeeds (e.g., running as root), that's fine
                except PermissionError:
                    pass  # Expected
            finally:
                os.chmod(memory_file, original_mode)

    def test_concurrent_corruption_scenario(self, test_config, test_email, memory_setup):
        """Test that atomic writes prevent corruption during concurrent ops."""
        with patch("src.memory.get_config", return_value=test_config):
            # Add initial facts
            for i in range(5):
                add_fact(test_email, f"Initial fact {i}", "initial")

            errors = []

            def writer():
                try:
                    for i in range(20):
                        add_fact(test_email, f"Concurrent fact {i}", "concurrent")
                except Exception as e:
                    errors.append(e)

            def reader():
                try:
                    for _ in range(20):
                        facts = get_all_facts(test_email)
                        # Each fact should be valid
                        for fact in facts:
                            assert fact.id is not None
                            assert fact.content is not None
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=writer),
                threading.Thread(target=writer),
                threading.Thread(target=reader),
                threading.Thread(target=reader),
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # No corruption errors
            assert len(errors) == 0, f"Errors: {errors}"

            # File should still be valid JSON
            facts = get_all_facts(test_email)
            assert len(facts) >= 5  # At least initial facts


class TestEdgeCases:
    """Additional edge case tests."""

    def test_id_collision_potential(self, test_config, test_email, memory_setup):
        """Test for potential ID collisions with rapid adds."""
        with patch("src.memory.get_config", return_value=test_config):
            # Add many facts very quickly to test ID generation
            ids = set()
            for i in range(100):
                fact = add_fact(test_email, f"Fact {i}", "test")
                if fact.id in ids:
                    pytest.fail(f"ID collision detected: {fact.id}")
                ids.add(fact.id)

            assert len(ids) == 100

    def test_very_long_email(self, test_config, memory_setup):
        """Test handling of very long email addresses.

        BUG FIXED: Very long email addresses are now truncated with a hash
        suffix to maintain uniqueness while staying within filesystem limits.
        """
        with patch("src.memory.get_config", return_value=test_config):
            # RFC 5321 allows 254 chars, but let's test longer
            long_email = "a" * 500 + "@example.com"

            # Now works - email is hashed to create valid filename
            fact = add_fact(long_email, "Test fact", "test")
            assert fact.content == "Test fact"

            # Verify we can retrieve it
            facts = get_all_facts(long_email)
            assert len(facts) == 1
            assert facts[0].content == "Test fact"

            # Verify filename is within limits
            memory_file = _get_memory_file(long_email)
            assert len(memory_file.name) <= 255  # Filesystem limit

    def test_special_email_characters(self, test_config, memory_setup):
        """Test email addresses with special characters."""
        with patch("src.memory.get_config", return_value=test_config):
            # Email with special chars that need sanitization
            special_emails = [
                "user+tag@example.com",
                "user.name@example.com",
                '"quoted"@example.com',
                "user@sub.domain.example.com",
            ]

            for email in special_emails:
                fact = add_fact(email, "Test fact", "test")
                facts = get_all_facts(email)
                assert len(facts) >= 1, f"Failed for email: {email}"

    def test_update_with_long_content(self, test_config, test_email, memory_setup):
        """Test updating fact with very long content."""
        with patch("src.memory.get_config", return_value=test_config):
            fact = add_fact(test_email, "Short content", "test")

            long_content = "X" * 10000
            result = update_fact(test_email, fact.id, long_content)
            assert result is True

            facts = get_all_facts(test_email)
            assert len(facts[0].content) == 10000

    def test_search_with_regex_chars(self, test_config, test_email, memory_setup):
        """Test search with regex special characters."""
        with patch("src.memory.get_config", return_value=test_config):
            # Add fact with regex-like content
            content = "Uses [regex] patterns like .* and (groups)"
            add_fact(test_email, content, "test")

            # Search should work (uses simple string matching, not regex)
            results = search_facts(test_email, "[regex]")
            assert len(results) == 1

            results = search_facts(test_email, ".*")
            assert len(results) == 1

    def test_large_number_of_facts(self, test_config, test_email, memory_setup):
        """Test handling large number of facts."""
        with patch("src.memory.get_config", return_value=test_config):
            num_facts = 1000

            for i in range(num_facts):
                add_fact(test_email, f"Fact number {i}", f"category_{i % 10}")

            facts = get_all_facts(test_email)
            assert len(facts) == num_facts

            # Search should still work
            results = search_facts(test_email, "Fact number 500")
            assert len(results) == 1

            # Category filter should work
            cat_facts = get_facts_by_category(test_email, "category_5")
            assert len(cat_facts) == 100  # 1000 / 10 categories

    def test_memory_lock_release_on_exception(self, test_config, test_email, memory_setup):
        """Test that lock is released even if operation fails."""
        with patch("src.memory.get_config", return_value=test_config):
            # First add a valid fact
            add_fact(test_email, "Valid fact", "test")

            # Simulate an error during save by patching
            with patch("src.memory._save_user_memory", side_effect=IOError("Disk full")):
                try:
                    add_fact(test_email, "Will fail", "test")
                except IOError:
                    pass

            # Lock should be released - this should not hang
            facts = get_all_facts(test_email)
            assert len(facts) == 1

    def test_concurrent_id_collision_potential(self, test_config, test_email, memory_setup):
        """Test for ID collisions in concurrent rapid adds.

        The ID is generated using datetime.now() with microseconds.
        Due to the global lock, IDs are unique. Duplicate detection
        prevents adding facts with identical content+category, so we
        use unique content per fact to test ID generation.
        """
        with patch("src.memory.get_config", return_value=test_config):
            all_ids = []
            errors = []
            counter = [0]  # Use list to allow mutation in nested function
            counter_lock = threading.Lock()

            def rapid_adds():
                try:
                    for _ in range(50):
                        # Use unique content to avoid duplicate detection
                        with counter_lock:
                            counter[0] += 1
                            unique_num = counter[0]
                        fact = add_fact(
                            test_email,
                            f"Unique fact {unique_num}",
                            "test",
                            allow_duplicate=True,  # Bypass duplicate check for this test
                        )
                        all_ids.append(fact.id)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=rapid_adds) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Errors: {errors}"

            # Check for ID duplicates (not content duplicates)
            unique_ids = set(all_ids)
            assert len(unique_ids) == len(all_ids), f"ID collision! {len(all_ids)} total, {len(unique_ids)} unique"

    def test_email_with_slashes(self, test_config, memory_setup):
        """Test email addresses with forward slashes.

        Note: While rare, technically allowed in the local part of email addresses
        when quoted. The _get_memory_file function now sanitizes slashes to
        prevent subdirectory creation.
        """
        with patch("src.memory.get_config", return_value=test_config):
            # This email would have created a subdirectory if slashes weren't handled
            email_with_slash = "user/name@example.com"
            memory_file = _get_memory_file(email_with_slash)

            # The filename should NOT contain slashes (they're replaced with _)
            assert "/" not in memory_file.name
            # The sanitized path should contain "user_name"
            assert "user_name" in memory_file.name
