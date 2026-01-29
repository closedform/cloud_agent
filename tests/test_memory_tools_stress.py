"""Stress tests for memory tools - edge cases and potential bugs."""

import pytest
from unittest.mock import patch


class TestRecallFactsNoMatches:
    """Tests for recall_facts when no matches are found."""

    def test_recall_facts_no_matches_with_query(self, test_config):
        """Search for facts that don't exist returns empty list with message."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query="unicorn")

            assert result["status"] == "success"
            assert result["facts"] == []
            assert "No facts found for 'unicorn'" in result["message"]

    def test_recall_facts_empty_user_memory(self, test_config):
        """Search when user has no facts at all."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="newuser@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query="anything")

            assert result["status"] == "success"
            assert result["facts"] == []
            assert "No facts found" in result["message"]

    def test_recall_facts_no_query_empty_memory(self, test_config):
        """Recall all facts when memory is empty."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="emptyuser@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query="")

            assert result["status"] == "success"
            assert result["facts"] == []
            assert "No facts found" in result["message"]

    def test_recall_facts_missing_user_email(self, test_config):
        """Recall fails without user email in context."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ):
            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query="test")

            assert result["status"] == "error"
            assert "No user email in context" in result["message"]


class TestVeryLongSearchQueries:
    """Tests for recall_facts with very long search queries."""

    def test_recall_facts_very_long_query(self, test_config):
        """Search with extremely long query string."""
        very_long_query = "a" * 10000  # 10k characters

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=very_long_query)

            # Should not crash, just return no matches
            assert result["status"] == "success"
            assert result["facts"] == []

    def test_recall_facts_query_with_newlines(self, test_config):
        """Search with query containing newlines."""
        query_with_newlines = "line1\nline2\nline3"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=query_with_newlines)

            # Should handle gracefully
            assert result["status"] == "success"

    def test_recall_facts_unicode_query(self, test_config):
        """Search with unicode/emoji characters."""
        unicode_query = "test with emoji and unicode characters"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=unicode_query)

            assert result["status"] == "success"

    def test_recall_facts_whitespace_only_query(self, test_config):
        """Search with whitespace-only query."""
        whitespace_query = "   \t\n   "

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts, remember_fact

            # First add a fact
            remember_fact(content="test fact", category="test", keywords="test")

            result = recall_facts(query=whitespace_query)

            # Whitespace query should match whitespace in content
            # This may or may not be desired behavior
            assert result["status"] == "success"


class TestSQLInjectionAttempts:
    """Tests for SQL injection attempts in search terms.

    Note: The memory module uses JSON file storage, not SQL,
    so SQL injection is not directly applicable. However, we should
    test that special characters don't cause issues.
    """

    def test_recall_facts_sql_injection_drop_table(self, test_config):
        """Attempt SQL injection with DROP TABLE."""
        injection_query = "'; DROP TABLE facts; --"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=injection_query)

            # Should not crash, just treat as literal string
            assert result["status"] == "success"

    def test_recall_facts_sql_injection_union_select(self, test_config):
        """Attempt SQL injection with UNION SELECT."""
        injection_query = "' UNION SELECT * FROM users --"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=injection_query)

            assert result["status"] == "success"

    def test_remember_fact_with_special_characters(self, test_config):
        """Store fact with SQL-like special characters."""
        injection_content = "User's cat named 'O\"Brien; DROP TABLE pets;--"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            result = remember_fact(
                content=injection_content,
                category="test",
                keywords="cat, injection"
            )

            assert result["status"] == "success"

            # Verify it was stored correctly
            recall_result = recall_facts(query="O\"Brien")
            assert recall_result["status"] == "success"
            # Should find the fact with special characters preserved
            if recall_result["facts"]:
                assert injection_content in recall_result["facts"][0]["content"]

    def test_recall_facts_json_injection(self, test_config):
        """Test JSON-like injection strings."""
        json_injection = '{"$ne": null}'

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query=json_injection)

            # Should not crash
            assert result["status"] == "success"

    def test_remember_fact_backslash_characters(self, test_config):
        """Store fact with backslash characters (JSON escape test)."""
        backslash_content = r"Path is C:\Users\test\Documents"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test body"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            result = remember_fact(
                content=backslash_content,
                category="locations",
                keywords="path, windows"
            )

            assert result["status"] == "success"

            # Verify backslashes are preserved
            recall_result = recall_facts(query="Documents")
            assert recall_result["status"] == "success"
            if recall_result["facts"]:
                assert "\\" in recall_result["facts"][0]["content"]


class TestForgetFactNonExistent:
    """Tests for forget_fact with non-existent facts."""

    def test_forget_fact_nonexistent_id(self, test_config):
        """Deleting a non-existent fact returns error."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import forget_fact

            result = forget_fact(fact_id="nonexistent_fact_12345")

            assert result["status"] == "error"
            assert "Fact not found" in result["message"]

    def test_forget_fact_empty_id(self, test_config):
        """Deleting with empty fact_id."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import forget_fact

            result = forget_fact(fact_id="")

            assert result["status"] == "error"
            assert "Fact not found" in result["message"]

    def test_forget_fact_from_another_user(self, test_config):
        """Try to delete another user's fact."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="user1@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            # User1 creates a fact
            result = remember_fact(content="User1's secret", category="secrets")
            fact_id = result["fact_id"]

        # Now try to delete as user2
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="user2@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import forget_fact

            result = forget_fact(fact_id=fact_id)

            # Should not find it (different user's fact)
            assert result["status"] == "error"
            assert "Fact not found" in result["message"]

    def test_forget_fact_missing_user_email(self, test_config):
        """Forget fails without user email in context."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ):
            from src.agents.tools.memory_tools import forget_fact

            result = forget_fact(fact_id="some_fact_id")

            assert result["status"] == "error"
            assert "No user email in context" in result["message"]

    def test_forget_fact_special_characters_in_id(self, test_config):
        """Try to delete with special characters in fact_id."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import forget_fact

            # Try various special character IDs
            special_ids = [
                "../../../etc/passwd",
                "fact'; DROP TABLE --",
                "fact\x00null",
                "fact<script>alert(1)</script>",
            ]

            for special_id in special_ids:
                result = forget_fact(fact_id=special_id)
                # Should not crash, just return not found
                assert result["status"] == "error"
                assert "Fact not found" in result["message"]


class TestRememberFactEdgeCases:
    """Edge cases for remember_fact function."""

    def test_remember_fact_empty_content(self, test_config):
        """Remember fact with empty content."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="", category="test")

            # Empty content may be allowed - check it doesn't crash
            assert "status" in result

    def test_remember_fact_empty_category(self, test_config):
        """Remember fact with empty category."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="Test fact", category="")

            # Empty category may be allowed
            assert "status" in result

    def test_remember_fact_very_long_content(self, test_config):
        """Remember fact with very long content."""
        very_long_content = "A" * 100000  # 100k characters

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content=very_long_content, category="test")

            # Should handle without crashing
            assert "status" in result

    def test_remember_fact_missing_user_email(self, test_config):
        """Remember fails without user email in context."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ):
            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="test", category="test")

            assert result["status"] == "error"
            assert "No user email in context" in result["message"]


class TestListFactsByCategoryEdgeCases:
    """Edge cases for list_facts_by_category function."""

    def test_list_facts_empty_category(self, test_config):
        """List facts with empty category string."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import list_facts_by_category

            result = list_facts_by_category(category="")

            assert result["status"] == "success"
            assert result["facts"] == []

    def test_list_facts_nonexistent_category(self, test_config):
        """List facts for category that doesn't exist."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import list_facts_by_category

            result = list_facts_by_category(category="nonexistent_category_xyz")

            assert result["status"] == "success"
            assert result["facts"] == []
            assert result["count"] == 0

    def test_list_facts_missing_user_email(self, test_config):
        """List fails without user email in context."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=""
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ):
            from src.agents.tools.memory_tools import list_facts_by_category

            result = list_facts_by_category(category="pets")

            assert result["status"] == "error"
            assert "No user email in context" in result["message"]

    def test_list_facts_case_sensitivity(self, test_config):
        """Test that category matching is case-insensitive."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, list_facts_by_category

            # Add fact with lowercase category
            remember_fact(content="Has a cat", category="pets")

            # Search with uppercase
            result = list_facts_by_category(category="PETS")

            assert result["status"] == "success"
            # The underlying implementation does case-insensitive matching
            assert result["count"] == 1


class TestCorruptedMemoryFile:
    """Tests for handling corrupted or malformed memory files."""

    def test_recall_facts_corrupted_json(self, test_config):
        """Recall facts when memory file contains invalid JSON."""
        # Create corrupted memory file
        memory_dir = test_config.project_root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "corrupted_at_example_com.json"
        memory_file.write_text("{ this is not valid json }")

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="corrupted@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=""
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import recall_facts

            result = recall_facts(query="test")

            # Should handle gracefully, return empty
            assert result["status"] == "success"
            assert result["facts"] == []

    def test_remember_fact_after_corrupted_file(self, test_config):
        """Remember fact when memory file was corrupted."""
        # Create corrupted memory file
        memory_dir = test_config.project_root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "corrupted2_at_example_com.json"
        memory_file.write_text("not json at all")

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="corrupted2@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            # This should overwrite the corrupted file
            result = remember_fact(content="New fact", category="test")

            # Should succeed and create valid file
            assert result["status"] == "success"


class TestPathTraversalViaEmail:
    """Tests for path traversal attempts via email address."""

    def test_email_with_path_traversal(self, test_config):
        """Email containing path traversal characters."""
        # This tests the email sanitization in _get_memory_file
        malicious_email = "../../../etc/passwd@example.com"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=malicious_email
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            result = remember_fact(content="Test", category="test")

            # Should succeed (email is sanitized)
            assert result["status"] == "success"

            # Verify we can recall it
            recall_result = recall_facts(query="Test")
            assert recall_result["status"] == "success"

    def test_email_with_null_bytes(self, test_config):
        """Email containing null bytes."""
        # Null bytes can be used to truncate filenames
        malicious_email = "user\x00.json@example.com"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=malicious_email
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="Test", category="test")

            # Should handle the null byte (might fail or sanitize)
            assert "status" in result

    def test_email_with_slashes_sanitized(self, test_config):
        """Forward slashes in email are now sanitized (BUG FIXED).

        The email sanitization in _get_memory_file now replaces forward slashes
        with underscores, preventing unintended subdirectory creation.
        """
        malicious_email = "user/deep/nested/path@example.com"

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value=malicious_email
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact
            from src.memory import _get_memory_file

            result = remember_fact(content="Test", category="test")

            # Succeeds without creating subdirectories
            assert result["status"] == "success"

            # Verify slashes are sanitized to underscores in filename
            memory_file = _get_memory_file(malicious_email)
            # Filename should NOT contain slashes
            assert "/" not in memory_file.name
            # Should be a flat file in memory/ directory
            assert memory_file.parent.name == "memory"


class TestKeywordsParsing:
    """Tests for keywords parameter parsing in remember_fact."""

    def test_remember_fact_empty_keywords(self, test_config):
        """Remember fact with empty keywords string."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            result = remember_fact(
                content="Fact without keywords",
                category="test",
                keywords=""
            )

            assert result["status"] == "success"

            # Should still be findable by content
            recall_result = recall_facts(query="without keywords")
            assert recall_result["status"] == "success"
            assert len(recall_result["facts"]) >= 1

    def test_remember_fact_keywords_with_extra_commas(self, test_config):
        """Remember fact with malformed keywords (extra commas)."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            result = remember_fact(
                content="Fact with weird keywords",
                category="test",
                keywords=",,key1,,key2,,,key3,,"
            )

            assert result["status"] == "success"

            # Should be findable by keyword
            recall_result = recall_facts(query="key2")
            assert recall_result["status"] == "success"
            assert len(recall_result["facts"]) >= 1

    def test_remember_fact_keywords_only_whitespace(self, test_config):
        """Remember fact with keywords that are only whitespace."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(
                content="Fact with whitespace keywords",
                category="test",
                keywords="   ,   ,   "
            )

            assert result["status"] == "success"


class TestSourceContextTruncation:
    """Tests for source_context truncation in remember_fact."""

    def test_remember_fact_long_body_truncated(self, test_config):
        """Verify that very long body is truncated in source_context."""
        very_long_body = "X" * 1000  # Longer than 200 char limit

        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value=very_long_body
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact
            from src.memory import get_all_facts

            result = remember_fact(content="Test truncation", category="test")

            assert result["status"] == "success"

            # Verify source_context was truncated
            facts = get_all_facts("test@example.com")
            # Find the fact we just added
            matching = [f for f in facts if f.content == "Test truncation"]
            assert len(matching) == 1
            # Source context should be truncated to 200 chars
            assert len(matching[0].source_context) <= 200


class TestDoubleDelete:
    """Tests for attempting to delete the same fact twice."""

    def test_forget_fact_twice(self, test_config):
        """Deleting the same fact twice should fail on second attempt."""
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, forget_fact

            # Create a fact
            result = remember_fact(content="To be deleted", category="test")
            fact_id = result["fact_id"]

            # First delete should succeed
            delete_result1 = forget_fact(fact_id=fact_id)
            assert delete_result1["status"] == "success"

            # Second delete should fail
            delete_result2 = forget_fact(fact_id=fact_id)
            assert delete_result2["status"] == "error"
            assert "Fact not found" in delete_result2["message"]


class TestPotentialDesignIssues:
    """Tests documenting design decisions and fixes."""

    def test_empty_content_rejected(self, test_config):
        """Empty content is now rejected with an error.

        Previously a bug, now fixed: empty facts provide no value.
        """
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="", category="test")

            # Now correctly rejects empty content
            assert result["status"] == "error"
            assert "empty" in result["message"].lower()

    def test_whitespace_only_content_rejected(self, test_config):
        """Whitespace-only content is now rejected.

        Previously a bug, now fixed: whitespace provides no meaningful information.
        """
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact

            result = remember_fact(content="   \t\n   ", category="test")

            # Now correctly rejects whitespace-only content
            assert result["status"] == "error"
            assert "empty" in result["message"].lower() or "whitespace" in result["message"].lower()

    def test_duplicate_facts_deduplicated(self, test_config):
        """Duplicate facts are now detected and deduplicated.

        Previously a bug, now fixed: identical content+category returns existing fact.
        """
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, recall_facts

            # Add the same fact twice
            result1 = remember_fact(content="Duplicate test", category="test")
            result2 = remember_fact(content="Duplicate test", category="test")

            assert result1["status"] == "success"
            assert result2["status"] == "success"
            # Both return the SAME fact ID (deduplication)
            assert result1["fact_id"] == result2["fact_id"]

            # Only one fact exists
            all_facts = recall_facts(query="Duplicate test")
            assert all_facts["count"] == 1

    def test_empty_category_allowed(self, test_config):
        """Empty category is still allowed (design decision).

        While not ideal, empty categories don't break functionality.
        The agent should be instructed to use meaningful categories.
        """
        with patch(
            "src.agents.tools.memory_tools.get_user_email", return_value="test@example.com"
        ), patch(
            "src.agents.tools.memory_tools.get_body", return_value="test"
        ), patch(
            "src.memory.get_config"
        ) as mock_get_config:
            mock_get_config.return_value = test_config

            from src.agents.tools.memory_tools import remember_fact, list_facts_by_category

            result = remember_fact(content="No category fact", category="")

            assert result["status"] == "success"

            # Can retrieve it with empty category
            category_facts = list_facts_by_category(category="")
            assert category_facts["count"] == 1
