"""File-based session store for conversation persistence."""

import json
import threading
from pathlib import Path
from typing import Any, Literal

from src.sessions.email_session import EmailConversation, compute_thread_id
from src.utils import atomic_write_json


class FileSessionStore:
    """Persists email conversations to a JSON file.

    Provides atomic read/write operations using temp file + rename pattern.
    """

    def __init__(self, file_path: Path):
        """Initialize the session store.

        Args:
            file_path: Path to the sessions JSON file.
        """
        self.file_path = file_path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load sessions from file."""
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
            # Validate structure
            if not isinstance(data, dict):
                print(f"Warning: Sessions file has invalid structure (expected dict), returning empty")
                return {}
            return data
        except json.JSONDecodeError as e:
            print(f"Warning: Sessions file has invalid JSON: {e}")
            return {}
        except OSError as e:
            print(f"Warning: Cannot read sessions file: {e}")
            return {}

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        """Save sessions atomically."""
        atomic_write_json(data, self.file_path)

    def get(self, thread_id: str) -> EmailConversation | None:
        """Get a conversation by thread ID.

        Args:
            thread_id: The thread identifier.

        Returns:
            EmailConversation if found, None otherwise.
        """
        with self._lock:
            data = self._load()
            if thread_id in data:
                return EmailConversation.from_dict(data[thread_id])
            return None

    def get_or_create(
        self, sender: str, subject: str
    ) -> tuple[EmailConversation, bool]:
        """Get existing conversation or create a new one.

        This method is atomic - the entire get-or-create cycle is protected
        by a lock to prevent race conditions when multiple tasks for the
        same thread arrive nearly simultaneously.

        Args:
            sender: Sender email address.
            subject: Email subject.

        Returns:
            Tuple of (conversation, is_new) where is_new is True if newly created.
        """
        thread_id = compute_thread_id(subject, sender)

        # Use lock to make entire get-or-create atomic
        with self._lock:
            data = self._load()

            if thread_id in data:
                return EmailConversation.from_dict(data[thread_id]), False

            # Create new conversation
            conversation = EmailConversation.create(sender, subject)
            data[thread_id] = conversation.to_dict()
            self._save(data)
            return conversation, True

    def save(self, conversation: EmailConversation) -> None:
        """Save a conversation.

        Args:
            conversation: The conversation to save.
        """
        with self._lock:
            data = self._load()
            data[conversation.thread_id] = conversation.to_dict()
            self._save(data)

    def add_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant"],
        content: str,
    ) -> bool:
        """Add a message to a conversation.

        Args:
            thread_id: The thread identifier.
            role: Message role ('user' or 'assistant').
            content: Message content.

        Returns:
            True if message was added, False if conversation not found.
        """
        with self._lock:
            data = self._load()
            if thread_id not in data:
                print(f"Warning: Conversation {thread_id} not found, cannot add message")
                return False

            try:
                conversation = EmailConversation.from_dict(data[thread_id])
                conversation.add_message(role, content)
                data[thread_id] = conversation.to_dict()
                self._save(data)
                return True
            except (KeyError, TypeError) as e:
                print(f"Warning: Failed to add message to {thread_id}: {e}")
                return False

    def list_conversations(
        self, sender: str | None = None, limit: int = 50
    ) -> list[EmailConversation]:
        """List conversations, optionally filtered by sender.

        Args:
            sender: Optional sender to filter by.
            limit: Maximum number to return.

        Returns:
            List of conversations, most recently updated first.
        """
        with self._lock:
            data = self._load()
            conversations = [EmailConversation.from_dict(c) for c in data.values()]

        # Filter by sender if specified
        if sender:
            sender_lower = sender.lower()
            conversations = [c for c in conversations if c.sender.lower() == sender_lower]

        # Sort by updated_at descending
        conversations.sort(key=lambda c: c.updated_at, reverse=True)

        return conversations[:limit]

    def delete(self, thread_id: str) -> bool:
        """Delete a conversation.

        Args:
            thread_id: The thread identifier.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            data = self._load()
            if thread_id not in data:
                return False

            del data[thread_id]
            self._save(data)
            return True

    def cleanup_old(self, days: int = 30) -> int:
        """Remove conversations older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of conversations deleted.
        """
        from datetime import datetime, timedelta

        with self._lock:
            data = self._load()
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()

            to_delete = []
            for thread_id, conv_data in data.items():
                if conv_data.get("updated_at", "") < cutoff_iso:
                    to_delete.append(thread_id)

            for thread_id in to_delete:
                del data[thread_id]

            if to_delete:
                self._save(data)

            return len(to_delete)
