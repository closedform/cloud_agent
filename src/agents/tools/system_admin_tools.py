"""System administration tool functions for SystemAdminAgent.

Provides scoped, safe tools for system administration tasks including
crontab management, system monitoring, and maintenance operations.

SECURITY: Sensitive operations (crontab, git, tests) require the user
to be in ADMIN_EMAILS. Read-only operations (disk, memory, processes)
are available to all allowed senders.
"""

import os
import subprocess
from typing import Any

from src.agents.tools._context import get_user_email
from src.config import get_config


def _is_admin() -> bool:
    """Check if current user is in admin_emails list."""
    config = get_config()
    user_email = get_user_email()
    return user_email in config.admin_emails


def _require_admin() -> dict[str, Any] | None:
    """Return error dict if user is not admin, None if they are."""
    if not _is_admin():
        return {
            "status": "error",
            "message": "This operation requires admin privileges. Contact the system administrator.",
        }
    return None


def _run_command(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command safely with timeout.

    Args:
        cmd: Command and arguments as list.
        timeout: Timeout in seconds.
        cwd: Working directory for the command.

    Returns:
        Tuple of (return_code, stdout, stderr).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


# === Crontab Management ===

# Allowlist of safe command patterns for crontab entries.
# Only commands matching these prefixes are permitted.
_CRONTAB_ALLOWED_COMMANDS = [
    "uv run python -m src.",  # Agent modules only
    "/usr/bin/curl",  # Curl for webhooks (full path, no shell)
]

# Shell metacharacters that could allow command injection
_SHELL_METACHARACTERS = [";", "&&", "||", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\\"]


def _is_command_allowed(command: str) -> bool:
    """Check if a crontab command is safe.

    Validates:
    1. Command matches an allowed prefix
    2. No shell metacharacters that could inject additional commands

    Only permits commands that match known safe patterns to prevent
    arbitrary code execution via email-triggered crontab modifications.
    """
    cmd_stripped = command.strip()

    # Block any shell metacharacters that could allow injection
    for char in _SHELL_METACHARACTERS:
        if char in cmd_stripped:
            return False

    # Check against allowlist prefixes
    for allowed in _CRONTAB_ALLOWED_COMMANDS:
        if cmd_stripped.startswith(allowed):
            return True
    return False


def list_crontabs() -> dict[str, Any]:
    """List all current user crontab entries.

    Returns:
        Dictionary with crontab entries.
    """
    code, stdout, stderr = _run_command(["crontab", "-l"])

    if code != 0:
        if "no crontab" in stderr.lower():
            return {
                "status": "success",
                "entries": [],
                "message": "No crontab entries found",
            }
        return {"status": "error", "message": stderr}

    entries = [line for line in stdout.strip().split("\n") if line and not line.startswith("#")]

    return {
        "status": "success",
        "entries": entries,
        "count": len(entries),
        "raw": stdout,
    }


def add_crontab_entry(
    schedule: str,
    command: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Add a new crontab entry. Requires admin privileges.

    Args:
        schedule: Cron schedule expression (e.g., "0 8 * * *" for daily at 8am).
        command: Command to run.
        comment: Optional comment to add above the entry.

    Returns:
        Dictionary with status.
    """
    if error := _require_admin():
        return error

    # Validate schedule format (basic check)
    parts = schedule.split()
    if len(parts) != 5:
        return {
            "status": "error",
            "message": f"Invalid cron schedule: expected 5 fields, got {len(parts)}",
        }

    # Security: Validate command against allowlist
    if not _is_command_allowed(command):
        return {
            "status": "error",
            "message": "Command not allowed. Only agent-related commands are permitted.",
        }

    # Get current crontab
    code, stdout, stderr = _run_command(["crontab", "-l"])
    if code != 0 and "no crontab" not in stderr.lower():
        return {"status": "error", "message": f"Failed to read crontab: {stderr}"}

    current = stdout if code == 0 else ""

    # Build new entry
    new_lines = []
    if comment:
        new_lines.append(f"# {comment}")
    new_lines.append(f"{schedule} {command}")
    new_entry = "\n".join(new_lines)

    # Append to current crontab
    current_stripped = current.rstrip()
    if current_stripped:
        new_crontab = current_stripped + "\n" + new_entry + "\n"
    else:
        new_crontab = new_entry + "\n"

    # Write new crontab
    try:
        proc = subprocess.Popen(
            ["crontab", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _, stderr = proc.communicate(input=new_crontab, timeout=10)

        if proc.returncode != 0:
            return {"status": "error", "message": f"Failed to set crontab: {stderr}"}

        return {
            "status": "success",
            "message": f"Added crontab entry: {schedule} {command}",
            "entry": new_entry,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def remove_crontab_entry(pattern: str) -> dict[str, Any]:
    """Remove crontab entries matching a pattern. Requires admin privileges.

    Args:
        pattern: Text pattern to match (case-insensitive substring match).

    Returns:
        Dictionary with status and removed entries.
    """
    if error := _require_admin():
        return error

    # Get current crontab
    code, stdout, stderr = _run_command(["crontab", "-l"])
    if code != 0:
        if "no crontab" in stderr.lower():
            return {"status": "success", "message": "No crontab to modify", "removed": []}
        return {"status": "error", "message": f"Failed to read crontab: {stderr}"}

    lines = stdout.split("\n")
    pattern_lower = pattern.lower()
    removed = []
    kept = []

    for line in lines:
        if pattern_lower in line.lower():
            removed.append(line)
        else:
            kept.append(line)

    if not removed:
        return {
            "status": "not_found",
            "message": f"No entries matching '{pattern}' found",
            "removed": [],
        }

    # Write new crontab
    new_crontab = "\n".join(kept)

    try:
        proc = subprocess.Popen(
            ["crontab", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _, stderr = proc.communicate(input=new_crontab, timeout=10)

        if proc.returncode != 0:
            return {"status": "error", "message": f"Failed to set crontab: {stderr}"}

        return {
            "status": "success",
            "message": f"Removed {len(removed)} crontab entry(ies)",
            "removed": removed,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# === System Monitoring ===


def check_disk_space() -> dict[str, Any]:
    """Check disk space usage.

    Returns:
        Dictionary with disk space information.
    """
    code, stdout, stderr = _run_command(["df", "-h"])

    if code != 0:
        return {"status": "error", "message": stderr}

    lines = stdout.strip().split("\n")
    # Parse df output
    disks = []
    for line in lines[1:]:  # Skip header
        parts = line.split()
        if len(parts) >= 6:
            disks.append({
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": parts[4],
                "mounted_on": parts[5],
            })

    return {
        "status": "success",
        "disks": disks,
        "raw": stdout,
    }


def check_memory() -> dict[str, Any]:
    """Check memory usage.

    Returns:
        Dictionary with memory information.
    """
    # Try vm_stat on macOS, free on Linux
    code, stdout, stderr = _run_command(["vm_stat"])

    if code == 0:
        # macOS
        return {
            "status": "success",
            "platform": "macos",
            "raw": stdout,
        }

    # Try Linux free command
    code, stdout, stderr = _run_command(["free", "-h"])
    if code == 0:
        return {
            "status": "success",
            "platform": "linux",
            "raw": stdout,
        }

    return {"status": "error", "message": "Could not determine memory usage"}


def list_running_processes(filter_pattern: str | None = None) -> dict[str, Any]:
    """List running processes, optionally filtered.

    Args:
        filter_pattern: Optional pattern to filter process names.

    Returns:
        Dictionary with process information.
    """
    code, stdout, stderr = _run_command(["ps", "aux"])

    if code != 0:
        return {"status": "error", "message": stderr}

    lines = stdout.strip().split("\n")
    processes = []

    for line in lines[1:]:  # Skip header
        if filter_pattern and filter_pattern.lower() not in line.lower():
            continue
        parts = line.split(None, 10)  # Split into max 11 parts
        if len(parts) >= 11:
            processes.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu": parts[2],
                "mem": parts[3],
                "command": parts[10],
            })

    return {
        "status": "success",
        "processes": processes[:50],  # Limit to 50
        "count": len(processes),
    }


# === Maintenance Operations ===


def check_git_status() -> dict[str, Any]:
    """Check git status of the project.

    Returns:
        Dictionary with git status information.
    """
    config = get_config()
    project_root = str(config.project_root)

    code, stdout, stderr = _run_command(["git", "-C", project_root, "status", "--porcelain"])

    if code != 0:
        return {"status": "error", "message": stderr}

    changes = stdout.strip().split("\n") if stdout.strip() else []

    # Get current branch
    code2, branch, _ = _run_command(["git", "-C", project_root, "branch", "--show-current"])
    current_branch = branch.strip() if code2 == 0 else "unknown"

    return {
        "status": "success",
        "branch": current_branch,
        "changes": changes,
        "is_clean": len(changes) == 0 or (len(changes) == 1 and changes[0] == ""),
    }


def git_pull() -> dict[str, Any]:
    """Pull latest changes from remote. Requires admin privileges.

    Returns:
        Dictionary with pull result.
    """
    if error := _require_admin():
        return error

    config = get_config()
    project_root = str(config.project_root)

    code, stdout, stderr = _run_command(["git", "-C", project_root, "pull"], timeout=60)

    if code != 0:
        return {"status": "error", "message": stderr}

    return {
        "status": "success",
        "message": stdout.strip(),
        "updated": "Already up to date" not in stdout,
    }


def run_tests(test_pattern: str | None = None) -> dict[str, Any]:
    """Run project tests. Requires admin privileges.

    Args:
        test_pattern: Optional pytest pattern (e.g., "test_diary" or "-k 'test_add'").

    Returns:
        Dictionary with test results.
    """
    if error := _require_admin():
        return error

    config = get_config()
    project_root = str(config.project_root)

    cmd = ["uv", "run", "pytest", "-v"]
    if test_pattern:
        if test_pattern.startswith("-"):
            cmd.extend(test_pattern.split())
        else:
            cmd.append(test_pattern)

    code, stdout, stderr = _run_command(cmd, timeout=300, cwd=project_root)

    # Parse results
    passed = stdout.count(" PASSED")
    failed = stdout.count(" FAILED")

    return {
        "status": "success" if code == 0 else "failed",
        "passed": passed,
        "failed": failed,
        "output": stdout[-5000:] if len(stdout) > 5000 else stdout,  # Limit output
        "return_code": code,
    }


def update_dependencies() -> dict[str, Any]:
    """Update project dependencies using uv. Requires admin privileges.

    Returns:
        Dictionary with update result.
    """
    if error := _require_admin():
        return error

    config = get_config()
    project_root = str(config.project_root)

    code, stdout, stderr = _run_command(
        ["uv", "sync"],
        timeout=120,
        cwd=project_root,
    )

    if code != 0:
        return {"status": "error", "message": stderr or stdout}

    return {
        "status": "success",
        "message": "Dependencies updated successfully",
        "output": stdout,
    }


def restart_services() -> dict[str, Any]:
    """Get instructions for restarting the agent services. Requires admin privileges.

    This doesn't actually restart (that would kill this process),
    but provides the commands needed.

    Returns:
        Dictionary with restart instructions.
    """
    if error := _require_admin():
        return error

    return {
        "status": "info",
        "message": "To restart the agent services, run the following commands on the VM:",
        "commands": [
            "tmux kill-session -t agent",
            "tmux new -s agent -d 'uv run python -m src.adk_orchestrator' \\; split-window -h 'uv run python -m src.poller'",
        ],
        "warning": "This will interrupt all current processing. Use with caution.",
    }
