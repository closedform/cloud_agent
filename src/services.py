"""Service container and factory for external services.

Encapsulates initialization of Gemini client and Calendar service,
removing import-time side effects from orchestrator.
"""

from dataclasses import dataclass
from typing import Any

from google import genai

from src.clients import calendar as calendar_client
from src.config import Config
from src.identities import Identity, get_identity


@dataclass
class Services:
    """Container for initialized external services."""

    gemini_client: genai.Client
    calendar_service: Any | None  # Google Calendar service or None
    calendars: dict[str, str]  # calendar_name -> calendar_id mapping

    def get_identity(self, email: str) -> Identity | None:
        """Get identity for an email address."""
        return get_identity(email)


def create_services(config: Config) -> Services:
    """Initialize and return all external services.

    This factory moves service initialization from module-level (import time)
    to explicit function call, preventing side effects on import.

    Raises:
        SystemExit: If GEMINI_API_KEY is not configured.
    """
    # Validate required config
    if not config.gemini_api_key:
        print("CRITICAL ERROR: GEMINI_API_KEY not found. Please set it in .env")
        raise SystemExit(1)

    # Initialize Gemini client
    gemini_client = genai.Client(api_key=config.gemini_api_key)

    # Initialize Calendar service
    calendar_service = None
    calendars = {"primary": "primary"}

    print("Loading calendars...")
    try:
        calendar_service = calendar_client.get_service(config)
        calendars = calendar_client.get_calendar_map(calendar_service)
        if "primary" not in calendars:
            calendars["primary"] = "primary"
        print(f"Loaded {len(calendars)} calendars: {list(calendars.keys())}")
    except Exception as e:
        print(f"WARNING: Could not load calendars ({e}). Using fallback.")

    return Services(
        gemini_client=gemini_client,
        calendar_service=calendar_service,
        calendars=calendars,
    )
