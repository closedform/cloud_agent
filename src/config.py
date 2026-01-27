"""Centralized configuration for the cloud agent.

All environment variables and paths are defined here. Use get_config() to access
configuration values - it loads dotenv once and caches the result.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _get_project_root() -> Path:
    """Find project root by locating pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to parent of src/
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    """Immutable configuration container."""

    # API Keys
    gemini_api_key: str

    # Model settings
    gemini_model: str
    gemini_research_model: str

    # Email settings
    email_user: str
    email_pass: str
    allowed_senders: tuple[str, ...]
    poll_interval: int
    imap_server: str
    smtp_server: str
    smtp_port: int

    # Paths (all anchored to project root)
    project_root: Path
    input_dir: Path
    processed_dir: Path
    failed_dir: Path
    reminders_file: Path
    token_path: Path
    credentials_path: Path

    # Task processing
    max_task_retries: int

    # Calendar settings
    timezone: str
    default_calendar: str


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and return configuration. Cached after first call."""
    project_root = _get_project_root()

    # Single load_dotenv call for entire application
    load_dotenv(project_root / ".env")

    # Parse allowed senders
    allowed_senders_env = os.getenv("ALLOWED_SENDERS", "")
    allowed_senders = tuple(s.strip() for s in allowed_senders_env.split(",") if s.strip())

    return Config(
        # API Keys
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),

        # Model settings
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        gemini_research_model=os.getenv("GEMINI_RESEARCH_MODEL", "gemini-2.5-flash"),

        # Email settings
        email_user=os.getenv("EMAIL_USER", ""),
        email_pass=os.getenv("EMAIL_PASS", ""),
        allowed_senders=allowed_senders,
        poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),

        # Paths
        project_root=project_root,
        input_dir=project_root / "inputs",
        processed_dir=project_root / "processed",
        failed_dir=project_root / "failed",
        reminders_file=project_root / "reminders.json",
        token_path=project_root / "token.json",
        credentials_path=project_root / "credentials.json",

        # Task processing
        max_task_retries=int(os.getenv("MAX_TASK_RETRIES", "3")),

        # Calendar settings
        timezone=os.getenv("TIMEZONE", "America/New_York"),
        default_calendar=os.getenv("DEFAULT_CALENDAR", "primary"),
    )
