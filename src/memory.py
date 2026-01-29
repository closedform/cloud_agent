"""Memory - persistent fact storage for user knowledge.

Stores facts about users extracted from conversations for later recall.
Examples: "Has cat named Oliver", "Uses Manhattan Vet on 5th Ave", "Prefers morning meetings"
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_config
from src.utils import atomic_write_json

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
    """Get the memory file path for a user.

    Sanitizes the email address to create a safe filename:
    - Replaces @ with _at_
    - Replaces . with _
    - Replaces / and \\ with _ to prevent directory traversal
    - Truncates/hashes very long emails to prevent OSError
    """
    import hashlib

    config = get_config()
    # Sanitize email for filename - handle path traversal characters
    safe_email = (
        email.replace("@", "_at_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    # Handle very long email addresses (filesystem limit is typically 255 bytes)
    # If the sanitized email is too long, hash it
    max_length = 200  # Leave room for .json extension and safety margin
    if len(safe_email) > max_length:
        # Use hash of original email to maintain uniqueness
        email_hash = hashlib.sha256(email.encode()).hexdigest()[:32]
        # Keep a prefix for readability + hash for uniqueness
        safe_email = f"{safe_email[:100]}_{email_hash}"

    return config.project_root / "memory" / f"{safe_email}.json"


def _load_user_memory(email: str) -> list[Fact]:
    """Load all facts for a user."""
    memory_file = _get_memory_file(email)
    if not memory_file.exists():
        return []

    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate that data is a list (not an object or other type)
        if not isinstance(data, list):
            print(f"Warning: Memory file for {email} contains non-list data, returning empty")
            return []
        return [Fact.from_dict(item) for item in data]
    except json.JSONDecodeError as e:
        print(f"Warning: Memory file for {email} has invalid JSON: {e}")
        return []
    except (KeyError, TypeError) as e:
        print(f"Warning: Memory file for {email} has invalid fact data: {e}")
        return []
    except UnicodeDecodeError as e:
        print(f"Warning: Memory file for {email} has encoding issues: {e}")
        return []
    except OSError as e:
        print(f"Warning: Cannot read memory file for {email}: {e}")
        return []


def _save_user_memory(email: str, facts: list[Fact]) -> None:
    """Save all facts for a user atomically."""
    memory_file = _get_memory_file(email)
    atomic_write_json([fact.to_dict() for fact in facts], memory_file)


def add_fact(
    email: str,
    content: str,
    category: str,
    source_context: str = "",
    keywords: list[str] | None = None,
    allow_duplicate: bool = False,
) -> Fact:
    """Add a new fact to user's memory.

    Args:
        email: User's email address
        content: The fact to store (e.g., "Has a cat named Oliver")
        category: Category for organization (e.g., "pets", "locations", "preferences")
        source_context: Original message that led to this fact
        keywords: Search keywords for this fact
        allow_duplicate: If False (default), skip adding if identical fact exists

    Returns:
        The created Fact object, or the existing Fact if duplicate found

    Raises:
        ValueError: If content is empty or whitespace-only
    """
    # Validate content is not empty or whitespace-only
    if not content or not content.strip():
        raise ValueError("Fact content cannot be empty or whitespace-only")

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

        # Check for duplicate (same content and category)
        if not allow_duplicate:
            for existing in facts:
                if (
                    existing.content.strip().lower() == content.strip().lower()
                    and existing.category.lower() == category.lower()
                ):
                    # Return the existing fact instead of creating duplicate
                    return existing

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

    Raises:
        ValueError: If content is empty or whitespace-only
    """
    # Validate content is not empty or whitespace-only
    if not content or not content.strip():
        raise ValueError("Fact content cannot be empty or whitespace-only")

    with _memory_lock:
        facts = _load_user_memory(email)
        for fact in facts:
            if fact.id == fact_id:
                fact.content = content
                _save_user_memory(email, facts)
                return True
        return False
