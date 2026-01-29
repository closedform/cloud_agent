"""Shared utility functions."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(data: Any, file_path: Path) -> None:
    """Write JSON data atomically using temp file + rename.

    Ensures data durability with fsync and cross-platform atomic rename.

    Args:
        data: JSON-serializable data to write.
        file_path: Target file path.
    """
    dir_path = file_path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def normalize_email(email: str) -> str:
    """Normalize email address for consistent storage and lookup.

    Lowercases the email to handle case-insensitive matching.
    Note: While RFC 5321 allows case-sensitive local parts, in practice
    email providers treat addresses as case-insensitive.

    Args:
        email: Email address to normalize.

    Returns:
        Normalized (lowercase, stripped) email address.
    """
    return email.strip().lower()
