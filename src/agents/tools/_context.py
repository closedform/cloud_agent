"""Global context for tool functions.

Tools need access to config and services, but ADK tool functions can't receive
custom parameters. This module provides thread-safe global access to these resources.
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
_request_context = threading.local()


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
    _request_context.user_email = user_email
    _request_context.thread_id = thread_id
    _request_context.reply_to = reply_to
    _request_context.body = body


def get_request_context() -> dict[str, str]:
    """Get the current request context.

    Returns:
        Dictionary with user_email, thread_id, reply_to, and body.
    """
    return {
        "user_email": getattr(_request_context, "user_email", ""),
        "thread_id": getattr(_request_context, "thread_id", ""),
        "reply_to": getattr(_request_context, "reply_to", ""),
        "body": getattr(_request_context, "body", ""),
    }


def clear_request_context() -> None:
    """Clear the current request context."""
    _request_context.user_email = ""
    _request_context.thread_id = ""
    _request_context.reply_to = ""
    _request_context.body = ""


# Convenience accessors for common context values
def get_user_email() -> str:
    """Get current user's email from request context."""
    return getattr(_request_context, "user_email", "")


def get_reply_to() -> str:
    """Get reply-to address from request context."""
    return getattr(_request_context, "reply_to", "")


def get_thread_id() -> str:
    """Get thread ID from request context."""
    return getattr(_request_context, "thread_id", "")


def get_body() -> str:
    """Get original message body from request context."""
    return getattr(_request_context, "body", "")

