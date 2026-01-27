"""Tests for the sessions module."""

import json
import pytest
from pathlib import Path

from src.sessions import (
    EmailConversation,
    FileSessionStore,
    Message,
    compute_thread_id,
)


class TestComputeThreadId:
    """Tests for compute_thread_id function."""

    def test_strips_re_prefix(self):
        """Should strip Re: prefix."""
        id1 = compute_thread_id("Test subject", "user@example.com")
        id2 = compute_thread_id("Re: Test subject", "user@example.com")
        assert id1 == id2

    def test_strips_fwd_prefix(self):
        """Should strip Fwd: prefix."""
        id1 = compute_thread_id("Test subject", "user@example.com")
        id2 = compute_thread_id("Fwd: Test subject", "user@example.com")
        assert id1 == id2

    def test_strips_multiple_prefixes(self):
        """Should strip multiple Re:/Fwd: prefixes."""
        id1 = compute_thread_id("Test subject", "user@example.com")
        id2 = compute_thread_id("Re: Re: Fwd: Test subject", "user@example.com")
        assert id1 == id2

    def test_case_insensitive(self):
        """Should be case-insensitive for subject."""
        id1 = compute_thread_id("Test Subject", "user@example.com")
        id2 = compute_thread_id("test subject", "user@example.com")
        assert id1 == id2

    def test_different_senders_different_threads(self):
        """Different senders should create different threads."""
        id1 = compute_thread_id("Test subject", "user1@example.com")
        id2 = compute_thread_id("Test subject", "user2@example.com")
        assert id1 != id2

    def test_returns_16_char_hex(self):
        """Should return a 16-character hex string."""
        thread_id = compute_thread_id("Test", "user@example.com")
        assert len(thread_id) == 16
        assert all(c in "0123456789abcdef" for c in thread_id)

    def test_strips_bracketed_prefixes(self):
        """Should strip [External] and similar prefixes."""
        id1 = compute_thread_id("Test subject", "user@example.com")
        id2 = compute_thread_id("[External] Test subject", "user@example.com")
        assert id1 == id2


class TestMessage:
    """Tests for Message dataclass."""

    def test_to_dict_includes_all_fields(self):
        """Should include all fields in dictionary."""
        msg = Message(role="user", content="Hello", timestamp="2026-01-27T10:00:00")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"
        assert d["timestamp"] == "2026-01-27T10:00:00"

    def test_from_dict_creates_message(self):
        """Should create message from dictionary."""
        d = {"role": "assistant", "content": "Hi there", "timestamp": "2026-01-27T10:01:00"}
        msg = Message.from_dict(d)
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
        assert msg.timestamp == "2026-01-27T10:01:00"

    def test_roundtrip(self):
        """Should preserve data through to_dict/from_dict roundtrip."""
        original = Message(role="user", content="Test message")
        restored = Message.from_dict(original.to_dict())
        assert restored.role == original.role
        assert restored.content == original.content


class TestEmailConversation:
    """Tests for EmailConversation dataclass."""

    def test_create_generates_thread_id(self):
        """Should generate thread_id from sender and subject."""
        conv = EmailConversation.create("user@example.com", "Test subject")
        expected_id = compute_thread_id("Test subject", "user@example.com")
        assert conv.thread_id == expected_id

    def test_add_message(self):
        """Should add messages to conversation."""
        conv = EmailConversation.create("user@example.com", "Test")
        conv.add_message("user", "Hello")
        conv.add_message("assistant", "Hi there")
        assert len(conv.messages) == 2
        assert conv.messages[0].content == "Hello"
        assert conv.messages[1].content == "Hi there"

    def test_get_history_returns_all(self):
        """Should return all messages by default."""
        conv = EmailConversation.create("user@example.com", "Test")
        conv.add_message("user", "One")
        conv.add_message("assistant", "Two")
        conv.add_message("user", "Three")
        history = conv.get_history()
        assert len(history) == 3

    def test_get_history_respects_limit(self):
        """Should limit history when max_messages specified."""
        conv = EmailConversation.create("user@example.com", "Test")
        for i in range(5):
            conv.add_message("user", f"Message {i}")
        history = conv.get_history(max_messages=2)
        assert len(history) == 2
        assert history[0].content == "Message 3"
        assert history[1].content == "Message 4"

    def test_get_context_string(self):
        """Should format history as string."""
        conv = EmailConversation.create("user@example.com", "Test")
        conv.add_message("user", "Hello")
        conv.add_message("assistant", "Hi!")
        context = conv.get_context_string()
        assert "User: Hello" in context
        assert "Assistant: Hi!" in context

    def test_to_dict_from_dict_roundtrip(self):
        """Should preserve data through roundtrip."""
        original = EmailConversation.create("user@example.com", "Test subject")
        original.add_message("user", "Hello")
        original.add_message("assistant", "Hi")

        restored = EmailConversation.from_dict(original.to_dict())
        assert restored.thread_id == original.thread_id
        assert restored.sender == original.sender
        assert restored.subject == original.subject
        assert len(restored.messages) == 2


class TestFileSessionStore:
    """Tests for FileSessionStore."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a session store with temporary file."""
        return FileSessionStore(tmp_path / "sessions.json")

    def test_get_returns_none_for_missing(self, store):
        """Should return None for non-existent thread."""
        assert store.get("nonexistent") is None

    def test_save_and_get(self, store):
        """Should save and retrieve conversation."""
        conv = EmailConversation.create("user@example.com", "Test")
        conv.add_message("user", "Hello")
        store.save(conv)

        retrieved = store.get(conv.thread_id)
        assert retrieved is not None
        assert retrieved.sender == "user@example.com"
        assert len(retrieved.messages) == 1

    def test_get_or_create_creates_new(self, store):
        """Should create new conversation if not exists."""
        conv, is_new = store.get_or_create("user@example.com", "Test")
        assert is_new is True
        assert conv.sender == "user@example.com"

    def test_get_or_create_returns_existing(self, store):
        """Should return existing conversation."""
        conv1, is_new1 = store.get_or_create("user@example.com", "Test")
        conv2, is_new2 = store.get_or_create("user@example.com", "Re: Test")

        assert is_new1 is True
        assert is_new2 is False
        assert conv1.thread_id == conv2.thread_id

    def test_add_message(self, store):
        """Should add message to existing conversation."""
        conv, _ = store.get_or_create("user@example.com", "Test")
        store.add_message(conv.thread_id, "user", "Hello")
        store.add_message(conv.thread_id, "assistant", "Hi")

        retrieved = store.get(conv.thread_id)
        assert len(retrieved.messages) == 2

    def test_add_message_raises_for_missing(self, store):
        """Should raise KeyError for non-existent thread."""
        with pytest.raises(KeyError):
            store.add_message("nonexistent", "user", "Hello")

    def test_list_conversations(self, store):
        """Should list all conversations."""
        store.get_or_create("user1@example.com", "Test 1")
        store.get_or_create("user2@example.com", "Test 2")

        convs = store.list_conversations()
        assert len(convs) == 2

    def test_list_conversations_filters_by_sender(self, store):
        """Should filter by sender."""
        store.get_or_create("user1@example.com", "Test 1")
        store.get_or_create("user2@example.com", "Test 2")
        store.get_or_create("user1@example.com", "Test 3")

        convs = store.list_conversations(sender="user1@example.com")
        assert len(convs) == 2

    def test_delete(self, store):
        """Should delete conversation."""
        conv, _ = store.get_or_create("user@example.com", "Test")
        thread_id = conv.thread_id

        assert store.delete(thread_id) is True
        assert store.get(thread_id) is None

    def test_delete_returns_false_for_missing(self, store):
        """Should return False for non-existent thread."""
        assert store.delete("nonexistent") is False

    def test_persists_to_file(self, store, tmp_path):
        """Should persist data to file."""
        conv, _ = store.get_or_create("user@example.com", "Test")
        store.add_message(conv.thread_id, "user", "Hello")

        # Create new store pointing to same file
        store2 = FileSessionStore(tmp_path / "sessions.json")
        retrieved = store2.get(conv.thread_id)
        assert retrieved is not None
        assert len(retrieved.messages) == 1
