"""Agent-created task model.

Tasks created by agents for the system to execute (e.g., sending emails to
third parties). Distinct from email-originated Task objects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentTask:
    """Represents a task created by an agent for system execution.

    Unlike email-originated Tasks, AgentTasks are created programmatically
    by agents and executed directly by the orchestrator.
    """

    id: str
    action: str  # Action type: "send_email", etc.
    params: dict[str, Any]  # Action-specific parameters
    created_by: str  # Agent that created this task
    original_sender: str  # User who triggered the original request
    original_thread_id: str  # Thread context for provenance
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Marker to distinguish from email tasks
    task_type: str = field(default="agent_task")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_type": self.task_type,
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "created_by": self.created_by,
            "original_sender": self.original_sender,
            "original_thread_id": self.original_thread_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        """Create AgentTask from dictionary.

        Raises:
            ValueError: If required fields are missing or task_type is wrong.
        """
        if data.get("task_type") != "agent_task":
            raise ValueError("Not an agent task")

        required = ("id", "action", "params", "created_by", "original_sender", "original_thread_id")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        return cls(
            id=data["id"],
            action=data["action"],
            params=data["params"],
            created_by=data["created_by"],
            original_sender=data["original_sender"],
            original_thread_id=data["original_thread_id"],
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    @classmethod
    def is_agent_task(cls, data: dict[str, Any]) -> bool:
        """Check if a task dict is an agent task."""
        return data.get("task_type") == "agent_task"
