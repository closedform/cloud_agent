"""Atomic file I/O for task files.

Provides safe read/write operations to prevent race conditions between
the poller (writer) and orchestrator (reader).
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_task_atomic(task: dict[str, Any], path: Path) -> None:
    """Write task to file atomically using temp file + rename.

    This prevents the orchestrator from reading a partially-written file.
    """
    # Write to temp file in same directory (ensures same filesystem for rename)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(task, f, indent=2)

        # Atomic rename (POSIX guarantees this is atomic on same filesystem)
        os.rename(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_task_safe(path: Path) -> dict[str, Any] | None:
    """Read task file safely, returning None on any failure.

    This handles cases where:
    - File doesn't exist
    - File is being written (partial content)
    - File contains invalid JSON
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
