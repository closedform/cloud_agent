"""Memory tools for storing and retrieving user facts."""

from typing import Any

from src.agents.tools._context import get_user_email, get_body
from src.memory import (
    add_fact,
    delete_fact,
    get_all_facts,
    get_facts_by_category,
    search_facts,
    update_fact,
)


def remember_fact(
    content: str,
    category: str,
    keywords: str = "",
) -> dict[str, Any]:
    """Store a fact about the user for future reference.

    Use this to remember important information the user mentions that might be
    useful later. Examples:
    - "Has a cat named Oliver" (category: "pets", keywords: "cat, oliver")
    - "Goes to Manhattan Vet on 5th Ave" (category: "locations", keywords: "vet, veterinarian")
    - "Prefers morning meetings" (category: "preferences", keywords: "meetings, schedule")
    - "Sister's name is Emily" (category: "people", keywords: "sister, emily, family")

    Args:
        content: The fact to remember (clear, concise statement)
        category: Category for organization. Common categories:
            - "pets": Pet information (names, types, vets)
            - "people": Family, friends, contacts
            - "locations": Places they go, addresses
            - "preferences": Likes, dislikes, habits
            - "health": Medical info, doctors
            - "work": Job, colleagues, projects
        keywords: Comma-separated keywords for searching (e.g., "cat, oliver, pet")

    Returns:
        Confirmation with the stored fact
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "No user email in context"}

    source_context = get_body()
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # Validate content before attempting to store
    if not content or not content.strip():
        return {"status": "error", "message": "Content cannot be empty or whitespace-only"}

    # Truncate source context for storage (avoid storing huge email bodies)
    truncated_context = source_context[:200] if source_context else ""

    try:
        fact = add_fact(
            email=email,
            content=content,
            category=category,
            source_context=truncated_context,
            keywords=keyword_list,
        )
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Failed to store fact: {e}"}

    return {
        "status": "success",
        "message": f"Remembered: {content}",
        "fact_id": fact.id,
        "category": category,
    }


def recall_facts(query: str = "") -> dict[str, Any]:
    """Search user's memory for relevant facts.

    Use this when the user asks about something they've mentioned before,
    or when you need context about them.

    Examples:
    - User asks "where's my vet?" -> recall_facts("vet")
    - User asks "what's my cat's name?" -> recall_facts("cat")
    - User mentions a person -> recall_facts("emily") to get context

    Args:
        query: Search term to find relevant facts. Leave empty to get all facts.

    Returns:
        List of matching facts with their content and categories
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "No user email in context"}

    try:
        if query:
            facts = search_facts(email, query)
        else:
            facts = get_all_facts(email)
    except Exception as e:
        return {"status": "error", "message": f"Failed to search facts: {e}"}

    if not facts:
        return {
            "status": "success",
            "facts": [],
            "message": "No facts found" + (f" for '{query}'" if query else ""),
        }

    return {
        "status": "success",
        "facts": [
            {
                "id": f.id,
                "content": f.content,
                "category": f.category,
                "keywords": f.keywords,
            }
            for f in facts
        ],
        "count": len(facts),
    }


def list_facts_by_category(category: str) -> dict[str, Any]:
    """Get all facts in a specific category.

    Args:
        category: Category to retrieve (pets, people, locations, preferences, health, work)

    Returns:
        List of facts in that category
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "No user email in context"}

    try:
        facts = get_facts_by_category(email, category)
    except Exception as e:
        return {"status": "error", "message": f"Failed to retrieve facts: {e}"}

    return {
        "status": "success",
        "category": category,
        "facts": [
            {
                "id": f.id,
                "content": f.content,
                "keywords": f.keywords,
            }
            for f in facts
        ],
        "count": len(facts),
    }


def forget_fact(fact_id: str) -> dict[str, Any]:
    """Delete a fact from memory.

    Use when the user wants to remove stored information or when
    information is no longer accurate.

    Args:
        fact_id: ID of the fact to delete (from recall_facts results)

    Returns:
        Confirmation of deletion
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "No user email in context"}

    try:
        if delete_fact(email, fact_id):
            return {"status": "success", "message": "Fact deleted"}
        else:
            return {"status": "error", "message": "Fact not found"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to delete fact: {e}"}


def update_fact_content(fact_id: str, content: str) -> dict[str, Any]:
    """Update the content of an existing fact.

    Use when the user provides corrected or updated information about
    something already stored.

    Args:
        fact_id: ID of the fact to update (from recall_facts results)
        content: New content to replace the existing fact content

    Returns:
        Confirmation of update
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "No user email in context"}

    # Validate content
    if not content or not content.strip():
        return {"status": "error", "message": "Content cannot be empty or whitespace-only"}

    try:
        if update_fact(email, fact_id, content):
            return {"status": "success", "message": f"Fact updated to: {content}"}
        else:
            return {"status": "error", "message": "Fact not found"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to update fact: {e}"}

