"""Atomic file I/O for task files.

Provides safe read/write operations to prevent race conditions between
the poller (writer) and orchestrator (reader).
"""

import json
from pathlib import Path
from typing import Any

from src.utils import atomic_write_json


def write_task_atomic(task: dict[str, Any], path: Path) -> None:
    """Write task to file atomically.

    This prevents the orchestrator from reading a partially-written file.
    """
    atomic_write_json(task, path)


def read_task_safe(path: Path) -> dict[str, Any] | None:
    """Read task file safely, returning None on any failure.

    This handles cases where:
    - File doesn't exist
    - File was deleted between glob and read
    - File contains invalid JSON
    - File has encoding issues

    Note: Partial reads are prevented by the atomic write pattern in
    write_task_atomic(), so we don't need to handle that case here.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
