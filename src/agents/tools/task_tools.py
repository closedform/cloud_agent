"""Task creation tools for agents.

Allows agents to create tasks for the system to execute, such as sending
emails to third parties.
"""

import uuid
from typing import Any

from src.agents.tools._context import get_thread_id, get_user_email
from src.config import get_config
from src.models import AgentTask
from src.task_io import write_task_atomic


def create_agent_task(
    action: str,
    params: dict[str, Any],
    created_by: str = "unknown",
) -> dict[str, Any]:
    """Create a task for the system to execute.

    Use this to perform system actions like sending emails to third parties.

    Supported actions:
    - "send_email": Send email to a recipient
        Required params: to_address, subject, body
        Optional params: icon (emoji for HTML header, default: message emoji)

    Args:
        action: Action type (e.g., "send_email").
        params: Action-specific parameters.
        created_by: Name of the agent creating this task.

    Returns:
        Dictionary with status and task ID.
    """
    config = get_config()

    # Validate action type
    valid_actions = {"send_email"}
    if action not in valid_actions:
        return {
            "status": "error",
            "message": f"Invalid action: {action}. Valid actions: {', '.join(valid_actions)}",
        }

    # Validate action-specific params
    if action == "send_email":
        required = ["to_address", "subject", "body"]
        missing = [p for p in required if p not in params]
        if missing:
            return {
                "status": "error",
                "message": f"Missing required params for send_email: {', '.join(missing)}",
            }

        # Validate values are non-empty strings (not None, empty, or whitespace-only)
        to_address = params["to_address"]
        subject = params["subject"]
        body = params["body"]

        empty_fields = []
        if not isinstance(to_address, str) or not to_address.strip():
            empty_fields.append("to_address")
        if not isinstance(subject, str) or not subject.strip():
            empty_fields.append("subject")
        if not isinstance(body, str) or not body.strip():
            empty_fields.append("body")

        if empty_fields:
            return {
                "status": "error",
                "message": f"Empty or invalid values for: {', '.join(empty_fields)}",
            }

        # Validate recipient is in allowed list (case-insensitive per RFC 5321)
        allowed_recipients_lower = {s.lower() for s in config.allowed_senders}
        if to_address.lower() not in allowed_recipients_lower:
            return {
                "status": "error",
                "message": f"Recipient {to_address} not in allowed list. Cannot send to arbitrary addresses.",
            }

    # Get provenance from request context
    original_sender = get_user_email()
    original_thread_id = get_thread_id()

    if not original_sender or not original_sender.strip():
        return {
            "status": "error",
            "message": "No user context available. Cannot create task.",
        }

    # Security: Validate original_sender is in allowed_senders
    # This provides defense-in-depth - even if context is somehow spoofed,
    # the task won't be created for non-whitelisted senders
    allowed_senders_lower = {s.lower() for s in config.allowed_senders}
    if original_sender.lower() not in allowed_senders_lower:
        return {
            "status": "error",
            "message": "User not authorized to create agent tasks.",
        }

    # Create the agent task
    task_id = uuid.uuid4().hex
    agent_task = AgentTask(
        id=task_id,
        action=action,
        params=params,
        created_by=created_by,
        original_sender=original_sender,
        original_thread_id=original_thread_id,
    )

    # Write atomically to inputs directory
    task_file = config.input_dir / f"task_{task_id}.json"
    try:
        write_task_atomic(agent_task.to_dict(), task_file)
        print(f"Agent task created: {action} by {created_by} (id: {task_id})")
        return {
            "status": "success",
            "message": f"Task created: {action}",
            "task_id": task_id,
            "action": action,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create task: {e}",
        }
