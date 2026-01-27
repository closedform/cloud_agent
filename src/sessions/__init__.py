"""Session management for multi-turn email conversations."""

from src.sessions.email_session import EmailConversation, Message, compute_thread_id
from src.sessions.session_store import FileSessionStore

__all__ = [
    "EmailConversation",
    "FileSessionStore",
    "Message",
    "compute_thread_id",
]
