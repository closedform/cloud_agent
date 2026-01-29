"""Email tool functions for RouterAgent and all agents.

Handles email sending and conversation history.
"""

from typing import Any

from src.agents.tools._context import get_user_email, get_reply_to, get_thread_id
from src.clients.email import send_email, html_response, text_to_html
from src.config import get_config
from src.identities import get_identity


def send_email_response(
    subject: str,
    body: str,
    icon: str = "💬",
) -> dict[str, Any]:
    """Send an email response to the user.

    Args:
        subject: Email subject line.
        body: Email body text (will be converted to HTML).
        icon: Optional emoji icon for HTML header (default: 💬).

    Returns:
        Dictionary with send status.

    Security: Validates reply_to against allowed_senders whitelist.
    """
    reply_to = get_reply_to()
    if not reply_to:
        return {"status": "error", "message": "Reply address not available"}

    config = get_config()

    # Security: Validate recipient against allowed senders whitelist
    allowed_senders_lower = {s.lower() for s in config.allowed_senders}
    if reply_to.lower() not in allowed_senders_lower:
        print(f"Security: Blocked email response to non-whitelisted recipient: {reply_to}")
        return {"status": "error", "message": "Recipient not in allowed list"}

    try:
        # Generate HTML version
        html_content = text_to_html(body)
        html_body = html_response(html_content, title=subject, icon=icon)

        success = send_email(
            to_address=reply_to,
            subject=subject,
            body=body,
            email_user=config.email_user,
            email_pass=config.email_pass,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            html_body=html_body,
        )

        if success:
            print(f"SUCCESS: Email sent to {reply_to}")
            return {
                "status": "success",
                "message": f"Email sent to {reply_to}",
                "to": reply_to,
                "subject": subject,
            }
        else:
            print("ERROR: Failed to send email")
            return {"status": "error", "message": "Failed to send email"}

    except Exception as e:
        print(f"ERROR: Email exception: {e}")
        return {"status": "error", "message": f"Email error: {e}"}


def get_conversation_history(max_messages: int = 10) -> dict[str, Any]:
    """Get conversation history for the current thread.

    Args:
        max_messages: Maximum number of messages to retrieve.

    Returns:
        Dictionary with conversation history.
    """
    from src.sessions import FileSessionStore

    thread_id = get_thread_id()
    if not thread_id:
        return {
            "status": "success",
            "message": "No conversation history (new thread)",
            "messages": [],
        }

    config = get_config()
    session_store = FileSessionStore(config.sessions_file)
    conversation = session_store.get(thread_id)

    if not conversation:
        return {
            "status": "success",
            "message": "No conversation history found",
            "messages": [],
        }

    messages = conversation.get_history(max_messages)
    return {
        "status": "success",
        "thread_id": thread_id,
        "subject": conversation.subject,
        "messages": [m.to_dict() for m in messages],
        "total_messages": len(conversation.messages),
    }


def get_user_identity() -> dict[str, Any]:
    """Get identity information for the current user.

    Returns:
        Dictionary with user identity (name, etc.) or unknown indicator.
    """
    email = get_user_email()
    if not email:
        return {"status": "error", "message": "User email not available"}

    identity = get_identity(email)

    if identity:
        return {
            "status": "success",
            "known": True,
            "email": identity.email,
            "name": identity.name,
            "short_name": identity.short_name,
        }
    else:
        return {
            "status": "success",
            "known": False,
            "email": email,
        }


def lookup_recipient(name: str) -> dict[str, Any]:
    """Look up a known recipient by name to get their email address.

    Use this when the user wants to send an email to another person.
    Only returns recipients who are in the allowed senders list.

    Args:
        name: Name or partial name to search for (case-insensitive)

    Returns:
        Dictionary with matching recipients and their email addresses.
    """
    from src.identities import IDENTITIES
    from src.config import get_config

    config = get_config()
    name_lower = name.lower()

    # Normalize allowed_senders to lowercase for case-insensitive comparison
    allowed_senders_lower = {s.lower() for s in config.allowed_senders}

    matches = []
    for email, identity in IDENTITIES.items():
        # Only include recipients who are in allowed_senders (case-insensitive)
        if email.lower() not in allowed_senders_lower:
            continue

        # Match against name or short_name
        if (
            name_lower in identity.name.lower()
            or name_lower in identity.short_name.lower()
        ):
            matches.append({
                "email": identity.email,
                "name": identity.name,
                "short_name": identity.short_name,
            })

    if not matches:
        return {
            "status": "success",
            "found": False,
            "message": f"No known recipient found matching '{name}'. Only family members in the system can receive emails.",
            "recipients": [],
        }

    return {
        "status": "success",
        "found": True,
        "recipients": matches,
        "count": len(matches),
    }

