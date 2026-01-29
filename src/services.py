"""Service container and factory for external services.

Encapsulates initialization of Gemini client and Calendar service,
removing import-time side effects from orchestrator.
"""

import time
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

    def refresh_calendars(self, config: Config) -> bool:
        """Refresh the calendar map from the calendar service.

        Useful for recovering from transient calendar API failures.

        Args:
            config: Application configuration.

        Returns:
            True if calendars were refreshed successfully, False otherwise.
        """
        if self.calendar_service is None:
            return False

        try:
            new_calendars = calendar_client.get_calendar_map(self.calendar_service)
            if "primary" not in new_calendars:
                new_calendars["primary"] = "primary"
            # Update the calendars dict in place (dataclass is not frozen)
            self.calendars.clear()
            self.calendars.update(new_calendars)
            print(f"Refreshed {len(self.calendars)} calendars: {list(self.calendars.keys())}")
            return True
        except Exception as e:
            print(f"Failed to refresh calendars: {e}")
            return False


def create_services(config: Config) -> Services:
    """Initialize and return all external services.

    This factory moves service initialization from module-level (import time)
    to explicit function call, preventing side effects on import.

    Raises:
        SystemExit: If GEMINI_API_KEY is not configured or Gemini client
                    cannot be initialized after retries.
    """
    # Validate required config
    if not config.gemini_api_key:
        print("CRITICAL ERROR: GEMINI_API_KEY not found. Please set it in .env")
        raise SystemExit(1)

    # Initialize Gemini client with retry for transient failures
    gemini_client = _create_gemini_client_with_retry(config.gemini_api_key)

    # Initialize Calendar service
    calendar_service = None
    calendars: dict[str, str] = {"primary": "primary"}

    print("Loading calendars...")
    try:
        calendar_service = calendar_client.get_service(config)
        calendars = calendar_client.get_calendar_map(calendar_service)
        if "primary" not in calendars:
            calendars["primary"] = "primary"
        print(f"Loaded {len(calendars)} calendars: {list(calendars.keys())}")
    except Exception as e:
        print(f"WARNING: Could not load calendars ({e}). Using fallback.")
        # Reset calendar_service to None if calendar_map failed
        # This ensures consistent state: either both work or neither
        calendar_service = None

    return Services(
        gemini_client=gemini_client,
        calendar_service=calendar_service,
        calendars=calendars,
    )


def _create_gemini_client_with_retry(
    api_key: str,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> genai.Client:
    """Create Gemini client with retry logic for transient failures.

    Args:
        api_key: The Gemini API key.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        Initialized Gemini client.

    Raises:
        SystemExit: If client cannot be created after all retries.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            # Verify the client is functional by checking it was created
            # The genai.Client constructor is lightweight and doesn't make API calls,
            # so we just verify it was instantiated correctly
            if client is not None:
                return client
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Gemini client initialization failed (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                print(f"Gemini client initialization failed after {max_retries} attempts: {e}")

    # If we get here, all retries failed
    print("CRITICAL ERROR: Could not initialize Gemini client")
    raise SystemExit(1)
