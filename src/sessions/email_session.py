"""Email conversation model for tracking multi-turn conversations."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


def compute_thread_id(subject: str, sender: str) -> str:
    """Compute thread ID from normalized subject and sender.

    Strips common reply/forward prefixes and hashes the result for
    consistent thread identification across email replies.

    Args:
        subject: Email subject line.
        sender: Sender email address.

    Returns:
        16-character hex hash identifying the thread.
    """
    # Normalize subject: lowercase and strip Re:, Fwd:, Fw: prefixes
    normalized = subject.lower().strip()
    prefixes = ["re:", "fwd:", "fw:"]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip()
                changed = True

    # Also strip bracketed prefixes like [External] or [SPAM]
    normalized = re.sub(r"^\[[^\]]+\]\s*", "", normalized)

    # Create key from sender and normalized subject
    key = f"{sender.lower()}:{normalized}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class Message:
    """A single message in a conversation."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create Message from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class EmailConversation:
    """Represents an email conversation thread with history.

    Tracks all messages in a conversation for multi-turn context.
    """

    thread_id: str
    sender: str
    subject: str
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_message(self, role: Literal["user", "assistant"], content: str) -> None:
        """Add a message to the conversation."""
        self.messages.append(Message(role=role, content=content))
        self.updated_at = datetime.now().isoformat()

    def get_history(self, max_messages: int | None = None) -> list[Message]:
        """Get conversation history, optionally limited to recent messages."""
        if max_messages is None:
            return self.messages.copy()
        return self.messages[-max_messages:]

    def get_context_string(self, max_messages: int = 10) -> str:
        """Format conversation history as a string for LLM context.

        Args:
            max_messages: Maximum number of recent messages to include.

        Returns:
            Formatted string with conversation history.
        """
        history = self.get_history(max_messages)
        if not history:
            return ""

        lines = ["Previous conversation:"]
        for msg in history:
            role_label = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{role_label}: {msg.content}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "thread_id": self.thread_id,
            "sender": self.sender,
            "subject": self.subject,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailConversation":
        """Create EmailConversation from dictionary."""
        return cls(
            thread_id=data["thread_id"],
            sender=data["sender"],
            subject=data["subject"],
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    @classmethod
    def create(cls, sender: str, subject: str) -> "EmailConversation":
        """Factory method to create a new conversation."""
        thread_id = compute_thread_id(subject, sender)
        return cls(
            thread_id=thread_id,
            sender=sender,
            subject=subject,
        )
