"""Memory - persistent fact storage for user knowledge.

Stores facts about users extracted from conversations for later recall.
Examples: "Has cat named Oliver", "Uses Manhattan Vet on 5th Ave", "Prefers morning meetings"
"""

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_config

_memory_lock = threading.Lock()


@dataclass
class Fact:
    """A single fact about a user."""

    id: str
    content: str  # The fact itself, e.g., "Has a cat named Oliver"
    category: str  # e.g., "pets", "preferences", "locations", "people"
    created_at: str
    source_context: str = ""  # Original message that led to this fact
    keywords: list[str] = field(default_factory=list)  # For search

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at,
            "source_context": self.source_context,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fact":
        return cls(
            id=data["id"],
            content=data["content"],
            category=data["category"],
            created_at=data["created_at"],
            source_context=data.get("source_context", ""),
            keywords=data.get("keywords", []),
        )


def _get_memory_file(email: str) -> Path:
    """Get the memory file path for a user."""
    config = get_config()
    # Sanitize email for filename
    safe_email = email.replace("@", "_at_").replace(".", "_")
    return config.project_root / "memory" / f"{safe_email}.json"


def _load_user_memory(email: str) -> list[Fact]:
    """Load all facts for a user."""
    memory_file = _get_memory_file(email)
    if not memory_file.exists():
        return []

    try:
        with open(memory_file, "r") as f:
            data = json.load(f)
        return [Fact.from_dict(item) for item in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_user_memory(email: str, facts: list[Fact]) -> None:
    """Save all facts for a user atomically."""
    memory_file = _get_memory_file(email)
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for rename)
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=memory_file.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump([fact.to_dict() for fact in facts], f, indent=2)

        # Atomic rename (POSIX guarantees this is atomic on same filesystem)
        os.rename(tmp_path, str(memory_file))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_fact(
    email: str,
    content: str,
    category: str,
    source_context: str = "",
    keywords: list[str] | None = None,
) -> Fact:
    """Add a new fact to user's memory.

    Args:
        email: User's email address
        content: The fact to store (e.g., "Has a cat named Oliver")
        category: Category for organization (e.g., "pets", "locations", "preferences")
        source_context: Original message that led to this fact
        keywords: Search keywords for this fact

    Returns:
        The created Fact object
    """
    fact = Fact(
        id=f"fact_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        content=content,
        category=category,
        created_at=datetime.now().isoformat(),
        source_context=source_context,
        keywords=keywords or [],
    )

    with _memory_lock:
        facts = _load_user_memory(email)
        facts.append(fact)
        _save_user_memory(email, facts)

    return fact


def get_all_facts(email: str) -> list[Fact]:
    """Get all facts for a user.

    Args:
        email: User's email address

    Returns:
        List of all facts for the user
    """
    with _memory_lock:
        return _load_user_memory(email)


def search_facts(email: str, query: str) -> list[Fact]:
    """Search user's facts by keyword or content.

    Args:
        email: User's email address
        query: Search query (searches content and keywords)

    Returns:
        List of matching facts
    """
    query_lower = query.lower()
    facts = get_all_facts(email)

    matches = []
    for fact in facts:
        # Search in content
        if query_lower in fact.content.lower():
            matches.append(fact)
            continue

        # Search in keywords
        if any(query_lower in kw.lower() for kw in fact.keywords):
            matches.append(fact)
            continue

        # Search in category
        if query_lower in fact.category.lower():
            matches.append(fact)

    return matches


def get_facts_by_category(email: str, category: str) -> list[Fact]:
    """Get all facts in a category.

    Args:
        email: User's email address
        category: Category to filter by

    Returns:
        List of facts in that category
    """
    facts = get_all_facts(email)
    return [f for f in facts if f.category.lower() == category.lower()]


def delete_fact(email: str, fact_id: str) -> bool:
    """Delete a fact by ID.

    Args:
        email: User's email address
        fact_id: ID of the fact to delete

    Returns:
        True if deleted, False if not found
    """
    with _memory_lock:
        facts = _load_user_memory(email)
        original_count = len(facts)
        facts = [f for f in facts if f.id != fact_id]

        if len(facts) < original_count:
            _save_user_memory(email, facts)
            return True
        return False


def update_fact(email: str, fact_id: str, content: str) -> bool:
    """Update a fact's content.

    Args:
        email: User's email address
        fact_id: ID of the fact to update
        content: New content for the fact

    Returns:
        True if updated, False if not found
    """
    with _memory_lock:
        facts = _load_user_memory(email)
        for fact in facts:
            if fact.id == fact_id:
                fact.content = content
                _save_user_memory(email, facts)
                return True
        return False
