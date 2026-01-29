"""Global context for tool functions.

Tools need access to config and services, but ADK tool functions can't receive
custom parameters. This module provides thread-safe global access to these resources.

Design Notes:
- Services: Global singleton set once during orchestrator initialization.
- Request Context: Uses a shared dict (NOT threading.local) because ADK runs
  sub-agents in separate threads that need access to the same context values.
  Since tasks are processed sequentially by the orchestrator, this is safe.
  The scheduler thread does NOT use request context - it operates independently.
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services import Services

_lock = threading.Lock()
_services: "Services | None" = None


def set_services(services: "Services") -> None:
    """Set the global services instance.

    Should be called once during orchestrator initialization.

    Args:
        services: Initialized Services instance.
    """
    global _services
    with _lock:
        _services = services


def get_services() -> "Services | None":
    """Get the global services instance.

    Returns:
        Services instance or None if not initialized.
    """
    with _lock:
        return _services


# Current request context (set per-request)
# IMPORTANT: This is a shared dict, NOT thread-local. This is intentional because:
# 1. ADK runs sub-agents in separate threads that need access to the same context
# 2. Tasks are processed sequentially, so only one context is active at a time
# 3. The scheduler thread operates independently and doesn't use this context
_request_context: dict[str, str] = {}
_context_lock = threading.Lock()


def set_request_context(
    user_email: str,
    thread_id: str,
    reply_to: str,
    body: str = "",
) -> None:
    """Set the current request context.

    Called at the start of each request to provide user context to tools.

    Args:
        user_email: Current user's email address.
        thread_id: Current conversation thread ID.
        reply_to: Reply-to address for responses.
        body: Original message body for context.
    """
    with _context_lock:
        _request_context["user_email"] = user_email
        _request_context["thread_id"] = thread_id
        _request_context["reply_to"] = reply_to
        _request_context["body"] = body


def get_request_context() -> dict[str, str]:
    """Get the current request context.

    Returns:
        Dictionary with user_email, thread_id, reply_to, and body.
    """
    with _context_lock:
        return {
            "user_email": _request_context.get("user_email", ""),
            "thread_id": _request_context.get("thread_id", ""),
            "reply_to": _request_context.get("reply_to", ""),
            "body": _request_context.get("body", ""),
        }


def clear_request_context() -> None:
    """Clear the current request context."""
    with _context_lock:
        _request_context.clear()


# Convenience accessors for common context values
def get_user_email() -> str:
    """Get current user's email from request context."""
    with _context_lock:
        return _request_context.get("user_email", "")


def get_reply_to() -> str:
    """Get reply-to address from request context."""
    with _context_lock:
        return _request_context.get("reply_to", "")


def get_thread_id() -> str:
    """Get thread ID from request context."""
    with _context_lock:
        return _request_context.get("thread_id", "")


def get_body() -> str:
    """Get original message body from request context."""
    with _context_lock:
        return _request_context.get("body", "")

