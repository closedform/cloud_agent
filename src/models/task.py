"""Task and Reminder data models."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Task:
    """Represents an incoming task from the poller."""

    id: str
    subject: str
    body: str
    sender: str
    reply_to: str
    attachments: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    intent: str | None = None
    classification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "subject": self.subject,
            "body": self.body,
            "sender": self.sender,
            "reply_to": self.reply_to,
            "attachments": self.attachments,
            "created_at": self.created_at,
            "intent": self.intent,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create Task from dictionary.

        Raises:
            ValueError: If required fields are missing.
        """
        required = ("id", "subject", "body", "sender", "reply_to")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        return cls(
            id=data["id"],
            subject=data["subject"],
            body=data["body"],
            sender=data["sender"],
            reply_to=data["reply_to"],
            attachments=data.get("attachments", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            intent=data.get("intent"),
            classification=data.get("classification"),
        )

    @classmethod
    def create(
        cls,
        subject: str,
        body: str,
        sender: str,
        reply_to: str | None = None,
        attachments: list[str] | None = None,
    ) -> "Task":
        """Factory method to create a new task with auto-generated ID."""
        return cls(
            id=str(int(time.time() * 1000)),
            subject=subject,
            body=body,
            sender=sender,
            reply_to=reply_to or sender,
            attachments=attachments or [],
        )


@dataclass
class Reminder:
    """Represents a scheduled reminder."""

    id: str
    message: str
    datetime: str  # ISO 8601 format
    reply_to: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "message": self.message,
            "datetime": self.datetime,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reminder":
        """Create Reminder from dictionary.

        Raises:
            ValueError: If required fields are missing.
        """
        required = ("id", "message", "datetime", "reply_to")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        return cls(
            id=data["id"],
            message=data["message"],
            datetime=data["datetime"],
            reply_to=data["reply_to"],
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    @classmethod
    def create(
        cls,
        message: str,
        reminder_datetime: str,
        reply_to: str,
        task_id: str | None = None,
    ) -> "Reminder":
        """Factory method to create a new reminder."""
        return cls(
            id=task_id or str(int(time.time() * 1000)),
            message=message,
            datetime=reminder_datetime,
            reply_to=reply_to,
        )
