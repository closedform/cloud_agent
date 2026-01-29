"""Centralized configuration for the cloud agent.

All environment variables and paths are defined here. Use get_config() to access
configuration values - it loads dotenv once and caches the result.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _parse_int_env(name: str, default: int) -> int:
    """Parse an integer environment variable with fallback to default.

    Args:
        name: Environment variable name.
        default: Default value if not set or invalid.

    Returns:
        Parsed integer value or default.
    """
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _validate_timezone(tz_str: str, default: str = "America/New_York") -> str:
    """Validate a timezone string.

    Args:
        tz_str: Timezone string to validate.
        default: Default timezone if invalid.

    Returns:
        Valid timezone string.
    """
    try:
        ZoneInfo(tz_str)
        return tz_str
    except (KeyError, ValueError):
        return default


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
    admin_emails: tuple[str, ...]  # Emails allowed to use SystemAdminAgent
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
    reminder_log_file: Path
    user_data_file: Path
    rules_file: Path
    diary_file: Path
    triggered_file: Path
    sessions_file: Path
    token_path: Path
    credentials_path: Path

    # Task processing
    max_task_retries: int

    # Calendar settings
    timezone: str
    default_calendar: str


def _validate_required_env_vars() -> list[str]:
    """Check for missing required environment variables.

    Returns:
        List of missing variable names.
    """
    required = ["GEMINI_API_KEY", "EMAIL_USER", "EMAIL_PASS", "ALLOWED_SENDERS"]
    missing = []
    for var in required:
        value = os.getenv(var)
        if not value or not value.strip():
            missing.append(var)
    return missing


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and return configuration. Cached after first call.

    Warns if required environment variables are missing.
    """
    project_root = _get_project_root()

    # Single load_dotenv call for entire application
    load_dotenv(project_root / ".env")

    # Warn about missing required variables
    missing = _validate_required_env_vars()
    if missing:
        print(f"Warning: Missing required environment variables: {', '.join(missing)}")

    # Parse allowed senders
    allowed_senders_env = os.getenv("ALLOWED_SENDERS", "")
    allowed_senders = tuple(s.strip() for s in allowed_senders_env.split(",") if s.strip())

    # Parse admin emails (for SystemAdminAgent access)
    admin_emails_env = os.getenv("ADMIN_EMAILS", "")
    admin_emails = tuple(s.strip() for s in admin_emails_env.split(",") if s.strip())

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
        admin_emails=admin_emails,
        poll_interval=_parse_int_env("POLL_INTERVAL", 60),
        imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=_parse_int_env("SMTP_PORT", 587),

        # Paths
        project_root=project_root,
        input_dir=project_root / "inputs",
        processed_dir=project_root / "processed",
        failed_dir=project_root / "failed",
        reminders_file=project_root / "reminders.json",
        reminder_log_file=project_root / "reminder_log.json",
        user_data_file=project_root / "user_data.json",
        rules_file=project_root / "rules.json",
        diary_file=project_root / "diary.json",
        triggered_file=project_root / "triggered.json",
        sessions_file=project_root / "sessions.json",
        token_path=project_root / "token.json",
        credentials_path=project_root / "credentials.json",

        # Task processing
        max_task_retries=_parse_int_env("MAX_TASK_RETRIES", 3),

        # Calendar settings
        timezone=_validate_timezone(os.getenv("TIMEZONE", "America/New_York")),
        default_calendar=os.getenv("DEFAULT_CALENDAR", "primary"),
    )
