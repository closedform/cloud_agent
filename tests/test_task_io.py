"""Tests for src/task_io.py"""

import json

import pytest

from src.task_io import read_task_safe, write_task_atomic


class TestWriteTaskAtomic:
    """Tests for write_task_atomic function."""

    def test_creates_parent_directories(self, temp_dir):
        """Should create parent directories if they don't exist."""
        path = temp_dir / "subdir" / "task.json"
        task = {"id": "test", "data": "value"}
        write_task_atomic(task, path)
        assert path.exists()

    def test_writes_valid_json(self, temp_dir):
        """Should write valid JSON that can be read back."""
        path = temp_dir / "task.json"
        task = {"id": "123", "subject": "Test", "body": "Content"}
        write_task_atomic(task, path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == task

    def test_no_temp_files_remain(self, temp_dir):
        """Should not leave temporary files after successful write."""
        path = temp_dir / "task.json"
        task = {"id": "test"}
        write_task_atomic(task, path)
        tmp_files = list(temp_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrites_existing_file(self, temp_dir):
        """Should overwrite existing file."""
        path = temp_dir / "task.json"
        write_task_atomic({"version": 1}, path)
        write_task_atomic({"version": 2}, path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["version"] == 2


class TestReadTaskSafe:
    """Tests for read_task_safe function."""

    def test_returns_none_for_missing_file(self, temp_dir):
        """Should return None if file doesn't exist."""
        path = temp_dir / "nonexistent.json"
        result = read_task_safe(path)
        assert result is None

    def test_returns_none_for_invalid_json(self, temp_dir):
        """Should return None for invalid JSON."""
        path = temp_dir / "invalid.json"
        with open(path, "w") as f:
            f.write("not valid json {{{")
        result = read_task_safe(path)
        assert result is None

    def test_returns_none_for_partial_json(self, temp_dir):
        """Should return None for truncated JSON."""
        path = temp_dir / "partial.json"
        with open(path, "w") as f:
            f.write('{"id": "test", "incomplete":')
        result = read_task_safe(path)
        assert result is None

    def test_reads_valid_json(self, temp_dir):
        """Should read and return valid JSON."""
        path = temp_dir / "valid.json"
        expected = {"id": "123", "subject": "Test"}
        with open(path, "w") as f:
            json.dump(expected, f)
        result = read_task_safe(path)
        assert result == expected

    def test_returns_none_for_binary_file(self, temp_dir):
        """Should return None for binary content."""
        path = temp_dir / "binary.json"
        with open(path, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        result = read_task_safe(path)
        assert result is None


class TestAtomicWriteReadRoundtrip:
    """Integration tests for write and read together."""

    def test_roundtrip_preserves_data(self, temp_dir):
        """Write then read should preserve all data."""
        path = temp_dir / "task.json"
        task = {
            "id": "task-123",
            "subject": "Test Subject",
            "body": "Test body with unicode",
            "sender": "test@example.com",
            "attachments": ["file1.pdf", "file2.png"],
            "nested": {"key": "value"},
        }
        write_task_atomic(task, path)
        loaded = read_task_safe(path)
        assert loaded == task

    def test_handles_unicode(self, temp_dir):
        """Should handle unicode characters correctly."""
        path = temp_dir / "unicode.json"
        task = {"subject": "Meeting tomorrow", "body": "Cafe rendezvous"}
        write_task_atomic(task, path)
        loaded = read_task_safe(path)
        assert loaded == task

    def test_handles_empty_strings(self, temp_dir):
        """Should handle empty strings."""
        path = temp_dir / "empty.json"
        task = {"id": "1", "subject": "", "body": ""}
        write_task_atomic(task, path)
        loaded = read_task_safe(path)
        assert loaded == task
