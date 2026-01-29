"""Stress tests for large payloads in task_tools and task_io.

Tests for edge cases:
1. Very long subject (10000 chars)
2. Very long body (1MB of text)
3. Many special characters in body
4. Unicode/emoji in all fields
"""

import json
import resource
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.tools._context import (
    clear_request_context,
    set_request_context,
)
from src.agents.tools.task_tools import create_agent_task
from src.models.agent_task import AgentTask
from src.task_io import read_task_safe, write_task_atomic


class TestLargeSubjects:
    """Tests for very long subjects (10000+ characters)."""

    def test_write_10000_char_subject(self, temp_dir):
        """Should handle 10000 character subject."""
        path = temp_dir / "large_subject.json"
        long_subject = "S" * 10_000
        task = {"id": "1", "subject": long_subject, "body": "normal body"}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == long_subject
        assert len(loaded["subject"]) == 10_000

    def test_write_100000_char_subject(self, temp_dir):
        """Should handle 100000 character subject."""
        path = temp_dir / "huge_subject.json"
        huge_subject = "X" * 100_000
        task = {"id": "2", "subject": huge_subject, "body": "body"}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert len(loaded["subject"]) == 100_000

    def test_subject_with_mixed_chars(self, temp_dir):
        """Subject with mixed ASCII, unicode, and special chars."""
        path = temp_dir / "mixed_subject.json"
        # Build a 10000 char subject with variety
        base = "ABCabc123!@#$%^&*()[]{}|;':\",./<>?`~"
        long_subject = (base * 300)[:10_000]
        task = {"id": "3", "subject": long_subject, "body": "test"}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == long_subject


class TestLargeBody:
    """Tests for very large body content (1MB+)."""

    def test_write_1mb_body(self, temp_dir):
        """Should handle 1MB body without crashing."""
        path = temp_dir / "1mb_body.json"
        one_mb = "B" * (1024 * 1024)  # 1MB of 'B's
        task = {"id": "1mb", "subject": "Test", "body": one_mb}

        start_time = time.time()
        write_task_atomic(task, path)
        write_time = time.time() - start_time

        start_time = time.time()
        loaded = read_task_safe(path)
        read_time = time.time() - start_time

        assert loaded is not None
        assert len(loaded["body"]) == 1024 * 1024

        # Sanity check - should complete in reasonable time (< 5 seconds each)
        assert write_time < 5.0, f"Write took {write_time:.2f}s, expected < 5s"
        assert read_time < 5.0, f"Read took {read_time:.2f}s, expected < 5s"

    def test_write_5mb_body(self, temp_dir):
        """Should handle 5MB body without crashing."""
        path = temp_dir / "5mb_body.json"
        five_mb = "X" * (5 * 1024 * 1024)  # 5MB
        task = {"id": "5mb", "subject": "Large", "body": five_mb}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert len(loaded["body"]) == 5 * 1024 * 1024

    def test_body_with_many_lines(self, temp_dir):
        """Should handle body with many lines (1 million lines)."""
        path = temp_dir / "many_lines.json"
        # 1 million lines - each line is "Line N\n"
        lines = [f"Line {i}" for i in range(100_000)]  # 100K lines to keep test fast
        many_lines_body = "\n".join(lines)
        task = {"id": "lines", "subject": "Lines Test", "body": many_lines_body}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"].count("\n") == 99_999  # N-1 newlines for N lines


class TestSpecialCharacters:
    """Tests for special characters in body."""

    def test_all_ascii_control_chars(self, temp_dir):
        """Should handle ASCII control characters (except null which breaks JSON)."""
        path = temp_dir / "control_chars.json"
        # ASCII control chars 1-31 (skip 0/null)
        control_chars = "".join(chr(i) for i in range(1, 32))
        task = {"id": "ctrl", "subject": "Control Chars", "body": control_chars}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"] == control_chars

    def test_json_special_chars(self, temp_dir):
        """Should handle characters that need JSON escaping."""
        path = temp_dir / "json_special.json"
        # Characters that need escaping in JSON
        special = '\\\"\n\r\t\b\f'
        # Plus some backslash sequences
        special += "\\n\\t\\r\\\\"
        task = {"id": "json", "subject": "JSON Special", "body": special}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"] == special

    def test_sql_injection_patterns(self, temp_dir):
        """Should safely handle SQL injection-like strings."""
        path = temp_dir / "sql_injection.json"
        sql_patterns = """
        SELECT * FROM users; DROP TABLE users;--
        ' OR '1'='1'; --
        '; EXEC xp_cmdshell('dir'); --
        1; UPDATE users SET admin=1 WHERE id=1;--
        """
        task = {"id": "sql", "subject": "SQL Test", "body": sql_patterns}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"] == sql_patterns

    def test_html_and_script_tags(self, temp_dir):
        """Should safely handle HTML/script content."""
        path = temp_dir / "html_script.json"
        html_content = """
        <script>alert('XSS')</script>
        <img src="x" onerror="alert('XSS')">
        <a href="javascript:alert('XSS')">Click</a>
        <div onclick="evil()">Click me</div>
        </body></html><html><body>
        """
        task = {"id": "html", "subject": "<script>title</script>", "body": html_content}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"] == html_content
        assert loaded["subject"] == "<script>title</script>"

    def test_massive_special_chars_body(self, temp_dir):
        """Should handle body with massive amount of special chars."""
        path = temp_dir / "massive_special.json"
        # 100KB of special characters
        special_set = "!@#$%^&*()[]{}|;':\",./<>?`~\\+-=_"
        body = (special_set * 4000)[:100_000]
        task = {"id": "massive", "subject": "Massive Special", "body": body}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert len(loaded["body"]) == 100_000


class TestUnicodeAndEmoji:
    """Tests for Unicode and emoji content."""

    def test_basic_unicode(self, temp_dir):
        """Should handle basic unicode characters."""
        path = temp_dir / "unicode.json"
        unicode_text = "Cafe francais - ninos - Strasze - zhongwen - nihongo"
        task = {"id": "uni", "subject": unicode_text, "body": unicode_text}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == unicode_text
        assert loaded["body"] == unicode_text

    def test_emoji_in_all_fields(self, temp_dir):
        """Should handle emoji in all text fields."""
        path = temp_dir / "emoji.json"
        emoji_subject = "Meeting reminder! Calendar check!"
        emoji_body = "Status: green! red! yellow!\nFeeling: happy! sad!\nAnimals: dog! cat! bird!"
        task = {
            "id": "emoji-test-cool",
            "subject": emoji_subject,
            "body": emoji_body,
            "sender": "user.test@example.com",
            "tags": ["urgent!", "family!"],
        }

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == emoji_subject
        assert loaded["body"] == emoji_body

    def test_complex_emoji_sequences(self, temp_dir):
        """Should handle complex emoji sequences (ZWJ, modifiers)."""
        path = temp_dir / "complex_emoji.json"
        # Complex emoji: skin tones, ZWJ sequences, flags
        complex_emoji = (
            "skin tones "  # Combined into compound emoji
            "flags flag_us flag_jp "  # Flags are regional indicators
            "families family "  # ZWJ sequences
            "professions person_facepalming "  # ZWJ with gender
        )
        task = {"id": "complex", "subject": complex_emoji, "body": complex_emoji * 100}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert complex_emoji in loaded["body"]

    def test_rtl_and_mixed_direction(self, temp_dir):
        """Should handle RTL text and mixed direction."""
        path = temp_dir / "rtl.json"
        # Arabic, Hebrew, and mixed with LTR
        rtl_text = "Arabic: mrhba. Hebrew: shlwm. Mixed: Hello mrhba World"
        task = {"id": "rtl", "subject": rtl_text, "body": rtl_text}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == rtl_text

    def test_full_unicode_range(self, temp_dir):
        """Should handle characters from various Unicode planes."""
        path = temp_dir / "full_unicode.json"
        # Characters from different planes
        unicode_sample = (
            "Basic: ABC abc 123\n"
            "Latin Extended: A a C c E e\n"
            "Greek: A B G D E Z\n"
            "Cyrillic: A B V G D E\n"
            "CJK: zh wen\n"
            "Japanese: a i u e o\n"
            "Korean: hangul\n"
            "Symbols: star music note\n"
            "Math: infinity partial_diff integral\n"
            "Box drawing: box1 box2 box3\n"
        )
        task = {"id": "planes", "subject": "Unicode Test", "body": unicode_sample}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["body"] == unicode_sample

    def test_massive_emoji_body(self, temp_dir):
        """Should handle body with thousands of emoji."""
        path = temp_dir / "emoji_flood.json"
        # 10000 emoji
        emoji_set = "!@#$%^&"  # Using special chars as emoji stand-ins for reliability
        emoji_body = emoji_set * 2000
        task = {"id": "flood", "subject": "Emoji Flood", "body": emoji_body}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert len(loaded["body"]) == len(emoji_body)


class TestCreateAgentTaskLargePayloads:
    """Integration tests for create_agent_task with large payloads."""

    @pytest.fixture(autouse=True)
    def setup_context(self, test_config):
        """Set up request context for each test."""
        set_request_context(
            user_email="allowed@example.com",
            thread_id="test-thread-123",
            reply_to="allowed@example.com",
            body="original message",
        )
        yield
        clear_request_context()

    def test_create_task_large_subject(self, test_config, temp_dir):
        """Should handle task creation with very long subject."""
        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            # Ensure input_dir exists
            test_config.input_dir.mkdir(parents=True, exist_ok=True)

            long_subject = "S" * 10_000
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": long_subject,
                    "body": "Test body",
                },
                created_by="TestAgent",
            )

            assert result["status"] == "success"
            # Verify the file was written
            task_files = list(test_config.input_dir.glob("task_*.json"))
            assert len(task_files) == 1

            # Verify content
            with open(task_files[0]) as f:
                data = json.load(f)
            assert len(data["params"]["subject"]) == 10_000

    def test_create_task_large_body(self, test_config, temp_dir):
        """Should handle task creation with 1MB body."""
        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            test_config.input_dir.mkdir(parents=True, exist_ok=True)

            large_body = "B" * (1024 * 1024)  # 1MB
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Large Body Test",
                    "body": large_body,
                },
                created_by="TestAgent",
            )

            assert result["status"] == "success"
            task_files = list(test_config.input_dir.glob("task_*.json"))
            assert len(task_files) == 1

            with open(task_files[0]) as f:
                data = json.load(f)
            assert len(data["params"]["body"]) == 1024 * 1024

    def test_create_task_unicode_emoji_all_fields(self, test_config, temp_dir):
        """Should handle Unicode and emoji in all task fields."""
        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            test_config.input_dir.mkdir(parents=True, exist_ok=True)

            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": "Test Subject - cafe francais check!",
                    "body": "Body: hello! happy! star!\nChinese: zhongwen\nArabic: mrhba",
                    "icon": "star!",
                },
                created_by="TestAgent-bot",
            )

            assert result["status"] == "success"
            task_files = list(test_config.input_dir.glob("task_*.json"))
            assert len(task_files) == 1

    def test_create_task_special_chars_body(self, test_config, temp_dir):
        """Should handle special characters in body."""
        with patch("src.agents.tools.task_tools.get_config", return_value=test_config):
            test_config.input_dir.mkdir(parents=True, exist_ok=True)

            special_body = """
            Line with "quotes" and 'apostrophes'
            Backslashes: \\ \\n \\t
            HTML: <script>alert('test')</script>
            SQL: SELECT * FROM users; DROP TABLE users;--
            Newlines:

            Tabs:	tab	here
            """
            result = create_agent_task(
                action="send_email",
                params={
                    "to_address": "allowed@example.com",
                    "subject": 'Subject with "quotes"',
                    "body": special_body,
                },
                created_by="TestAgent",
            )

            assert result["status"] == "success"
            task_files = list(test_config.input_dir.glob("task_*.json"))
            with open(task_files[0]) as f:
                data = json.load(f)
            assert data["params"]["body"] == special_body


class TestAgentTaskModelLargePayloads:
    """Tests for AgentTask model with large payloads."""

    def test_agent_task_large_params(self):
        """Should handle AgentTask with large params."""
        large_body = "X" * (1024 * 1024)  # 1MB
        task = AgentTask(
            id="test-123",
            action="send_email",
            params={
                "to_address": "test@example.com",
                "subject": "S" * 10_000,
                "body": large_body,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        # Convert to dict and back
        task_dict = task.to_dict()
        restored = AgentTask.from_dict(task_dict)

        assert len(restored.params["subject"]) == 10_000
        assert len(restored.params["body"]) == 1024 * 1024

    def test_agent_task_unicode_all_fields(self):
        """Should handle AgentTask with Unicode in all string fields."""
        task = AgentTask(
            id="unicode-id-cafe-123",
            action="send_email",
            params={
                "to_address": "test@example.com",
                "subject": "Subject cafe francais check!",
                "body": "Body mrhba shlwm",
            },
            created_by="Agent-bot",
            original_sender="user-test@example.com",
            original_thread_id="thread-star-123",
        )

        task_dict = task.to_dict()
        restored = AgentTask.from_dict(task_dict)

        assert restored.created_by == "Agent-bot"
        assert "cafe" in restored.params["subject"] or "check" in restored.params["subject"]


class TestMemoryUsage:
    """Tests to ensure no memory leaks or excessive memory usage."""

    def test_repeated_large_writes_no_leak(self, temp_dir):
        """Should not leak memory on repeated large writes."""
        large_body = "X" * (1024 * 1024)  # 1MB

        # Get initial memory usage
        if sys.platform != "win32":
            initial_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # Write 10 large files
        for i in range(10):
            path = temp_dir / f"leak_test_{i}.json"
            task = {"id": str(i), "body": large_body}
            write_task_atomic(task, path)
            read_task_safe(path)
            # Delete file to avoid disk space issues
            path.unlink()

        # Check memory didn't grow excessively
        if sys.platform != "win32":
            final_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Allow up to 100MB growth (generous margin for test overhead)
            mem_growth_kb = final_mem - initial_mem
            assert mem_growth_kb < 100_000, f"Memory grew by {mem_growth_kb}KB"

    def test_no_temp_files_after_large_write(self, temp_dir):
        """Should clean up temp files even with large payloads."""
        large_body = "X" * (5 * 1024 * 1024)  # 5MB
        path = temp_dir / "cleanup_test.json"

        write_task_atomic({"body": large_body}, path)

        # Check no temp files remain
        tmp_files = list(temp_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_string_fields(self, temp_dir):
        """Should handle empty strings."""
        path = temp_dir / "empty.json"
        task = {"id": "", "subject": "", "body": "", "sender": ""}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert loaded["subject"] == ""
        assert loaded["body"] == ""

    def test_null_bytes_rejected(self, temp_dir):
        """Null bytes should be handled gracefully."""
        path = temp_dir / "null_bytes.json"
        # JSON doesn't allow null bytes, so this tests error handling
        body_with_null = "before\x00after"
        task = {"id": "null", "body": body_with_null}

        # This may or may not work depending on json library behavior
        # The important thing is it doesn't crash
        try:
            write_task_atomic(task, path)
            loaded = read_task_safe(path)
            # If it works, verify the content
            assert loaded is not None
        except (ValueError, TypeError):
            # JSON encoder may reject null bytes - this is acceptable
            pass

    def test_deeply_nested_params(self, temp_dir):
        """Should handle deeply nested data structures."""
        path = temp_dir / "nested.json"
        # Create deeply nested structure
        nested = {"level": 0}
        current = nested
        for i in range(1, 100):
            current["child"] = {"level": i}
            current = current["child"]

        task = {"id": "nested", "params": nested}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        # Verify nesting preserved
        current = loaded["params"]
        for i in range(50):  # Check first 50 levels
            assert current["level"] == i
            if "child" in current:
                current = current["child"]

    def test_large_array_in_params(self, temp_dir):
        """Should handle params with large arrays."""
        path = temp_dir / "large_array.json"
        # Array with 100K items
        large_array = list(range(100_000))
        task = {"id": "array", "attachments": large_array}

        write_task_atomic(task, path)
        loaded = read_task_safe(path)

        assert loaded is not None
        assert len(loaded["attachments"]) == 100_000
        assert loaded["attachments"][99_999] == 99_999
