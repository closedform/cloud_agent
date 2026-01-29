"""Tests for AgentTask serialization - data integrity testing.

Tests focus on:
1. Roundtrip with special characters in all fields
2. Roundtrip with None vs missing fields
3. from_dict with extra unexpected fields
4. to_dict produces valid JSON that can be written to file
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.models import AgentTask


class TestRoundtripSpecialCharacters:
    """Test roundtrip serialization with special characters in all fields."""

    def test_unicode_characters_in_all_string_fields(self):
        """Should preserve Unicode characters through roundtrip."""
        task = AgentTask(
            id="task-\u4e2d\u6587-\u0639\u0631\u0628\u064a",  # Chinese and Arabic
            action="send_\u00e9mail",  # accented e
            params={
                "to_address": "user@\u0435\u043c\u0430\u0438\u043b.com",  # Russian email
                "subject": "\ud83d\udce7 Test \u2603 \u2764",  # emojis and symbols
                "body": "Hello \u4e16\u754c \u0645\u0631\u062d\u0628\u0627",  # Chinese and Arabic
            },
            created_by="Agent\u00df",  # German eszett
            original_sender="user@\u00f1ame.com",  # n with tilde
            original_thread_id="thread-\u03b1\u03b2\u03b3",  # Greek letters
            created_at="2026-01-28T12:00:00",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.id == task.id
        assert restored.action == task.action
        assert restored.params == task.params
        assert restored.created_by == task.created_by
        assert restored.original_sender == task.original_sender
        assert restored.original_thread_id == task.original_thread_id

    def test_newlines_and_tabs_in_params(self):
        """Should preserve newlines and tabs in params."""
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "body": "Line 1\nLine 2\n\tIndented\r\nWindows line",
                "subject": "Tab\there",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.params["body"] == "Line 1\nLine 2\n\tIndented\r\nWindows line"
        assert restored.params["subject"] == "Tab\there"

    def test_json_special_characters(self):
        """Should handle JSON special characters (quotes, backslashes)."""
        task = AgentTask(
            id='task-with-"quotes"',
            action="send_email",
            params={
                "body": 'He said "Hello" and then \\n was printed',
                "path": "C:\\Users\\Name\\file.txt",
                "quote": "It's a 'test'",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.id == 'task-with-"quotes"'
        assert restored.params["body"] == 'He said "Hello" and then \\n was printed'
        assert restored.params["path"] == "C:\\Users\\Name\\file.txt"
        assert restored.params["quote"] == "It's a 'test'"

    def test_html_entities_and_angle_brackets(self):
        """Should preserve HTML entities and angle brackets."""
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "body": "<html>&lt;tag&gt; &amp; &quot;entity&quot;</html>",
                "subject": "Test <important>",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.params["body"] == "<html>&lt;tag&gt; &amp; &quot;entity&quot;</html>"
        assert restored.params["subject"] == "Test <important>"

    def test_null_bytes_and_control_characters(self):
        """Should handle control characters (excluding null which JSON can't handle)."""
        # Note: JSON spec doesn't allow \x00 (null byte), but other control chars work
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "body": "Bell\x07 Backspace\x08 FormFeed\x0c",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        # Verify JSON serialization works
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AgentTask.from_dict(parsed)

        assert restored.params["body"] == "Bell\x07 Backspace\x08 FormFeed\x0c"


class TestRoundtripNoneVsMissing:
    """Test handling of None values vs missing fields."""

    def test_from_dict_uses_default_for_missing_created_at(self):
        """Should use current time when created_at is missing."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": {"to_address": "test@example.com"},
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
            # created_at intentionally missing
        }

        task = AgentTask.from_dict(data)

        # Should have a valid ISO timestamp (not empty, not None)
        assert task.created_at is not None
        assert len(task.created_at) > 0
        assert "T" in task.created_at  # ISO format contains T

    def test_none_in_params_preserved(self):
        """Should preserve None values inside params dict."""
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "test@example.com",
                "cc": None,
                "bcc": None,
                "attachment": None,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.params["cc"] is None
        assert restored.params["bcc"] is None
        assert restored.params["attachment"] is None
        assert "cc" in restored.params  # Key should exist
        assert "bcc" in restored.params

    def test_empty_string_vs_missing(self):
        """Should distinguish empty strings from missing fields."""
        # Empty strings should be preserved
        data = {
            "task_type": "agent_task",
            "id": "",  # empty string
            "action": "send_email",
            "params": {"body": ""},  # empty body
            "created_by": "",  # empty
            "original_sender": "user@example.com",
            "original_thread_id": "",  # empty
            "created_at": "",  # empty
        }

        task = AgentTask.from_dict(data)

        assert task.id == ""
        assert task.params["body"] == ""
        assert task.created_by == ""
        assert task.original_thread_id == ""
        assert task.created_at == ""

    def test_nested_none_in_params(self):
        """Should handle nested None values in params."""
        task = AgentTask(
            id="task-123",
            action="complex_action",
            params={
                "outer": {
                    "inner": None,
                    "list_with_none": [1, None, 3],
                    "nested": {"deep": None},
                },
                "top_level_none": None,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AgentTask.from_dict(parsed)

        assert restored.params["outer"]["inner"] is None
        assert restored.params["outer"]["list_with_none"] == [1, None, 3]
        assert restored.params["outer"]["nested"]["deep"] is None
        assert restored.params["top_level_none"] is None


class TestFromDictExtraFields:
    """Test from_dict behavior with extra unexpected fields."""

    def test_extra_fields_are_ignored(self):
        """Should ignore extra fields not in the dataclass."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": {"to_address": "test@example.com"},
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
            "created_at": "2026-01-28T12:00:00",
            # Extra fields that don't exist in dataclass
            "unknown_field": "should be ignored",
            "extra_number": 42,
            "extra_dict": {"nested": "value"},
            "extra_list": [1, 2, 3],
        }

        task = AgentTask.from_dict(data)

        assert task.id == "task-123"
        assert task.action == "send_email"
        # Verify no AttributeError and extra fields don't appear
        assert not hasattr(task, "unknown_field")
        assert not hasattr(task, "extra_number")
        assert not hasattr(task, "extra_dict")
        assert not hasattr(task, "extra_list")

    def test_extra_fields_do_not_corrupt_data(self):
        """Extra fields should not affect roundtrip of valid fields."""
        data = {
            "task_type": "agent_task",
            "id": "task-456",
            "action": "custom_action",
            "params": {"key": "value", "nested": {"a": 1}},
            "created_by": "AgentX",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-789",
            "created_at": "2026-01-28T15:30:00",
            # Extra fields
            "version": "2.0",
            "metadata": {"source": "test"},
        }

        task = AgentTask.from_dict(data)
        exported = task.to_dict()

        # Extra fields should not appear in exported dict
        assert "version" not in exported
        assert "metadata" not in exported

        # Valid fields should be preserved
        assert exported["id"] == "task-456"
        assert exported["params"]["nested"]["a"] == 1

    def test_extra_field_with_same_name_as_method(self):
        """Should handle extra fields that might conflict with method names."""
        data = {
            "task_type": "agent_task",
            "id": "task-123",
            "action": "send_email",
            "params": {},
            "created_by": "TestAgent",
            "original_sender": "user@example.com",
            "original_thread_id": "thread-123",
            # Fields that shadow method names
            "to_dict": "not a method",
            "from_dict": "also not a method",
            "is_agent_task": True,
        }

        task = AgentTask.from_dict(data)

        # Methods should still work
        assert callable(task.to_dict)
        result = task.to_dict()
        assert isinstance(result, dict)


class TestToDictJsonValidity:
    """Test that to_dict produces valid JSON that can be written to file."""

    def test_to_dict_is_json_serializable(self):
        """to_dict output should be directly serializable to JSON."""
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "to_address": "test@example.com",
                "subject": "Test",
                "body": "Hello world",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()

        # Should not raise
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

        # Should be parseable
        parsed = json.loads(json_str)
        assert parsed["id"] == "task-123"

    def test_write_to_file_and_read_back(self):
        """Should be able to write to file and read back correctly."""
        task = AgentTask(
            id="task-file-test",
            action="send_email",
            params={
                "to_address": "test@example.com",
                "body": "Content with\nnewlines\tand\ttabs",
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(task.to_dict(), f)
            temp_path = f.name

        try:
            with open(temp_path) as f:
                loaded_data = json.load(f)

            restored = AgentTask.from_dict(loaded_data)

            assert restored.id == task.id
            assert restored.action == task.action
            assert restored.params == task.params
            assert restored.created_by == task.created_by
        finally:
            Path(temp_path).unlink()

    def test_complex_nested_params_json_valid(self):
        """Complex nested params should produce valid JSON."""
        task = AgentTask(
            id="task-complex",
            action="complex_action",
            params={
                "string": "value",
                "number": 42,
                "float": 3.14159,
                "bool_true": True,
                "bool_false": False,
                "null_value": None,
                "list": [1, "two", 3.0, None, True],
                "nested_dict": {
                    "level1": {
                        "level2": {
                            "level3": ["deep", "array"],
                        },
                    },
                },
                "empty_dict": {},
                "empty_list": [],
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        json_str = json.dumps(data, indent=2)

        # Verify valid JSON
        parsed = json.loads(json_str)
        assert parsed["params"]["nested_dict"]["level1"]["level2"]["level3"] == [
            "deep",
            "array",
        ]

    def test_large_content_serialization(self):
        """Should handle large content without corruption."""
        large_body = "A" * 100000  # 100KB of text
        large_list = list(range(10000))

        task = AgentTask(
            id="task-large",
            action="send_email",
            params={
                "body": large_body,
                "data": large_list,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AgentTask.from_dict(parsed)

        assert len(restored.params["body"]) == 100000
        assert len(restored.params["data"]) == 10000
        assert restored.params["body"] == large_body
        assert restored.params["data"] == large_list

    def test_special_float_values(self):
        """Should handle special float values appropriately."""
        # Note: JSON spec doesn't support Infinity or NaN, so these would fail
        # This test documents the expected behavior
        task = AgentTask(
            id="task-floats",
            action="calculate",
            params={
                "normal": 1.5,
                "negative": -42.0,
                "scientific": 1.23e10,
                "small": 1.23e-10,
                "zero": 0.0,
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AgentTask.from_dict(parsed)

        assert restored.params["normal"] == 1.5
        assert restored.params["negative"] == -42.0
        assert restored.params["scientific"] == 1.23e10
        assert restored.params["zero"] == 0.0


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_params_dict(self):
        """Should handle empty params dict."""
        task = AgentTask(
            id="task-empty-params",
            action="no_op",
            params={},
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.params == {}

    def test_params_with_only_empty_values(self):
        """Should handle params with all empty/falsy values."""
        task = AgentTask(
            id="task-123",
            action="send_email",
            params={
                "empty_string": "",
                "zero": 0,
                "false": False,
                "none": None,
                "empty_list": [],
                "empty_dict": {},
            },
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.params["empty_string"] == ""
        assert restored.params["zero"] == 0
        assert restored.params["false"] is False
        assert restored.params["none"] is None
        assert restored.params["empty_list"] == []
        assert restored.params["empty_dict"] == {}

    def test_task_type_preserved_exactly(self):
        """task_type should always be exactly 'agent_task'."""
        task = AgentTask(
            id="task-123",
            action="test",
            params={},
            created_by="TestAgent",
            original_sender="user@example.com",
            original_thread_id="thread-123",
        )

        data = task.to_dict()
        assert data["task_type"] == "agent_task"

        restored = AgentTask.from_dict(data)
        assert restored.task_type == "agent_task"

    def test_very_long_string_fields(self):
        """Should handle very long strings in all fields."""
        long_string = "x" * 10000

        task = AgentTask(
            id=long_string,
            action=long_string[:1000],  # action might have limits
            params={"body": long_string},
            created_by=long_string[:500],
            original_sender=long_string[:500] + "@example.com",
            original_thread_id=long_string,
        )

        data = task.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AgentTask.from_dict(parsed)

        assert len(restored.id) == 10000
        assert len(restored.params["body"]) == 10000
