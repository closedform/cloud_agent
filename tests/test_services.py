"""Tests for src/services.py"""

from unittest.mock import MagicMock, patch

import pytest

from src.identities import Identity
from src.services import Services, create_services
from tests.conftest import TestConfig


class TestServicesDataclass:
    """Tests for the Services dataclass."""

    def test_services_has_required_fields(self):
        """Services should have all required fields."""
        mock_client = MagicMock()
        mock_calendar = MagicMock()
        calendars = {"primary": "primary", "work": "work_id"}

        services = Services(
            gemini_client=mock_client,
            calendar_service=mock_calendar,
            calendars=calendars,
        )

        assert services.gemini_client is mock_client
        assert services.calendar_service is mock_calendar
        assert services.calendars == calendars

    def test_services_with_none_calendar(self):
        """Services should allow None calendar_service."""
        mock_client = MagicMock()

        services = Services(
            gemini_client=mock_client,
            calendar_service=None,
            calendars={"primary": "primary"},
        )

        assert services.gemini_client is mock_client
        assert services.calendar_service is None
        assert services.calendars == {"primary": "primary"}

    def test_services_calendars_can_be_empty(self):
        """Services should allow empty calendars dict."""
        mock_client = MagicMock()

        services = Services(
            gemini_client=mock_client,
            calendar_service=None,
            calendars={},
        )

        assert services.calendars == {}


class TestServicesGetIdentity:
    """Tests for Services.get_identity method."""

    def test_get_identity_returns_identity_for_known_email(self):
        """Should return Identity for registered email."""
        mock_client = MagicMock()
        services = Services(
            gemini_client=mock_client,
            calendar_service=None,
            calendars={"primary": "primary"},
        )

        # Test with a known email from identities module
        identity = services.get_identity("dinunnob@gmail.com")
        assert identity is not None
        assert isinstance(identity, Identity)
        assert identity.short_name == "Brandon"

    def test_get_identity_returns_none_for_unknown_email(self):
        """Should return None for unregistered email."""
        mock_client = MagicMock()
        services = Services(
            gemini_client=mock_client,
            calendar_service=None,
            calendars={"primary": "primary"},
        )

        identity = services.get_identity("unknown@example.com")
        assert identity is None

    @patch("src.services.get_identity")
    def test_get_identity_delegates_to_module_function(self, mock_get_identity):
        """Should delegate to identities.get_identity function."""
        mock_identity = Identity(
            email="test@example.com",
            name="Test User",
            short_name="Test",
        )
        mock_get_identity.return_value = mock_identity

        mock_client = MagicMock()
        services = Services(
            gemini_client=mock_client,
            calendar_service=None,
            calendars={"primary": "primary"},
        )

        result = services.get_identity("test@example.com")

        mock_get_identity.assert_called_once_with("test@example.com")
        assert result is mock_identity


class TestCreateServices:
    """Tests for create_services factory function."""

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_creates_services_with_all_components(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should create Services with Gemini client and calendar."""
        mock_gemini = MagicMock()
        mock_genai_client.return_value = mock_gemini
        mock_calendar = MagicMock()
        mock_get_service.return_value = mock_calendar
        mock_get_calendar_map.return_value = {"primary": "primary", "work": "work_id"}

        services = create_services(test_config)

        assert services.gemini_client is mock_gemini
        assert services.calendar_service is mock_calendar
        assert services.calendars == {"primary": "primary", "work": "work_id"}

        mock_genai_client.assert_called_once_with(api_key=test_config.gemini_api_key)
        mock_get_service.assert_called_once_with(test_config)
        mock_get_calendar_map.assert_called_once_with(mock_calendar)

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_adds_primary_if_missing_from_calendars(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should add 'primary' calendar if not in calendar map."""
        mock_genai_client.return_value = MagicMock()
        mock_get_service.return_value = MagicMock()
        # Return calendars without 'primary'
        mock_get_calendar_map.return_value = {"work": "work_id", "personal": "personal_id"}

        services = create_services(test_config)

        # 'primary' should be added
        assert "primary" in services.calendars
        assert services.calendars["primary"] == "primary"
        assert services.calendars["work"] == "work_id"
        assert services.calendars["personal"] == "personal_id"

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_preserves_existing_primary_calendar(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should preserve 'primary' if already in calendar map."""
        mock_genai_client.return_value = MagicMock()
        mock_get_service.return_value = MagicMock()
        mock_get_calendar_map.return_value = {"primary": "custom_primary_id"}

        services = create_services(test_config)

        assert services.calendars["primary"] == "custom_primary_id"


class TestCreateServicesMissingApiKey:
    """Tests for create_services with missing GEMINI_API_KEY."""

    def test_raises_system_exit_when_api_key_missing(self, temp_dir):
        """Should raise SystemExit if GEMINI_API_KEY is empty."""
        config_without_key = TestConfig(
            gemini_api_key="",  # Empty API key
            project_root=temp_dir,
            input_dir=temp_dir / "inputs",
            processed_dir=temp_dir / "processed",
            failed_dir=temp_dir / "failed",
            reminders_file=temp_dir / "reminders.json",
            reminder_log_file=temp_dir / "reminder_log.json",
            user_data_file=temp_dir / "user_data.json",
            rules_file=temp_dir / "rules.json",
            diary_file=temp_dir / "diary.json",
            triggered_file=temp_dir / "triggered.json",
            sessions_file=temp_dir / "sessions.json",
            token_path=temp_dir / "token.json",
            credentials_path=temp_dir / "credentials.json",
        )

        with pytest.raises(SystemExit) as exc_info:
            create_services(config_without_key)

        assert exc_info.value.code == 1

    @patch("builtins.print")
    def test_prints_error_message_when_api_key_missing(self, mock_print, temp_dir):
        """Should print error message when API key is missing."""
        config_without_key = TestConfig(
            gemini_api_key="",
            project_root=temp_dir,
            input_dir=temp_dir / "inputs",
            processed_dir=temp_dir / "processed",
            failed_dir=temp_dir / "failed",
            reminders_file=temp_dir / "reminders.json",
            reminder_log_file=temp_dir / "reminder_log.json",
            user_data_file=temp_dir / "user_data.json",
            rules_file=temp_dir / "rules.json",
            diary_file=temp_dir / "diary.json",
            triggered_file=temp_dir / "triggered.json",
            sessions_file=temp_dir / "sessions.json",
            token_path=temp_dir / "token.json",
            credentials_path=temp_dir / "credentials.json",
        )

        with pytest.raises(SystemExit):
            create_services(config_without_key)

        mock_print.assert_any_call(
            "CRITICAL ERROR: GEMINI_API_KEY not found. Please set it in .env"
        )


class TestCreateServicesCalendarFailure:
    """Tests for create_services when calendar initialization fails."""

    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_handles_calendar_service_exception(
        self, mock_genai_client, mock_get_service, test_config
    ):
        """Should handle exception from calendar service initialization."""
        mock_gemini = MagicMock()
        mock_genai_client.return_value = mock_gemini
        mock_get_service.side_effect = Exception("No token.json found")

        services = create_services(test_config)

        # Should still create services with fallback values
        assert services.gemini_client is mock_gemini
        assert services.calendar_service is None
        assert services.calendars == {"primary": "primary"}

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_handles_calendar_map_exception(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should handle exception from get_calendar_map."""
        mock_gemini = MagicMock()
        mock_genai_client.return_value = mock_gemini
        mock_calendar = MagicMock()
        mock_get_service.return_value = mock_calendar
        mock_get_calendar_map.side_effect = Exception("API error")

        services = create_services(test_config)

        # Should still create services with fallback calendars
        # Note: calendar_service is set before get_calendar_map is called,
        # so it retains the value from get_service even when get_calendar_map fails
        assert services.gemini_client is mock_gemini
        assert services.calendar_service is mock_calendar
        assert services.calendars == {"primary": "primary"}

    @patch("builtins.print")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_prints_warning_on_calendar_failure(
        self, mock_genai_client, mock_get_service, mock_print, test_config
    ):
        """Should print warning when calendar initialization fails."""
        mock_genai_client.return_value = MagicMock()
        mock_get_service.side_effect = Exception("OAuth expired")

        create_services(test_config)

        # Should have printed loading message and warning
        mock_print.assert_any_call("Loading calendars...")
        mock_print.assert_any_call(
            "WARNING: Could not load calendars (OAuth expired). Using fallback."
        )


class TestCreateServicesConfiguration:
    """Tests for proper service configuration in create_services."""

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_passes_api_key_to_gemini_client(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, temp_dir
    ):
        """Should pass correct API key to Gemini client."""
        mock_get_calendar_map.return_value = {"primary": "primary"}
        mock_get_service.return_value = MagicMock()

        custom_api_key = "my-secret-api-key-12345"
        config = TestConfig(
            gemini_api_key=custom_api_key,
            project_root=temp_dir,
            input_dir=temp_dir / "inputs",
            processed_dir=temp_dir / "processed",
            failed_dir=temp_dir / "failed",
            reminders_file=temp_dir / "reminders.json",
            reminder_log_file=temp_dir / "reminder_log.json",
            user_data_file=temp_dir / "user_data.json",
            rules_file=temp_dir / "rules.json",
            diary_file=temp_dir / "diary.json",
            triggered_file=temp_dir / "triggered.json",
            sessions_file=temp_dir / "sessions.json",
            token_path=temp_dir / "token.json",
            credentials_path=temp_dir / "credentials.json",
        )

        create_services(config)

        mock_genai_client.assert_called_once_with(api_key=custom_api_key)

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_passes_config_to_calendar_service(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should pass config to calendar service initialization."""
        mock_genai_client.return_value = MagicMock()
        mock_calendar = MagicMock()
        mock_get_service.return_value = mock_calendar
        mock_get_calendar_map.return_value = {"primary": "primary"}

        create_services(test_config)

        mock_get_service.assert_called_once_with(test_config)

    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_passes_calendar_service_to_get_calendar_map(
        self, mock_genai_client, mock_get_service, mock_get_calendar_map, test_config
    ):
        """Should pass calendar service to get_calendar_map."""
        mock_genai_client.return_value = MagicMock()
        mock_calendar = MagicMock()
        mock_get_service.return_value = mock_calendar
        mock_get_calendar_map.return_value = {"primary": "primary"}

        create_services(test_config)

        mock_get_calendar_map.assert_called_once_with(mock_calendar)

    @patch("builtins.print")
    @patch("src.services.calendar_client.get_calendar_map")
    @patch("src.services.calendar_client.get_service")
    @patch("src.services.genai.Client")
    def test_prints_loaded_calendars_count(
        self,
        mock_genai_client,
        mock_get_service,
        mock_get_calendar_map,
        mock_print,
        test_config,
    ):
        """Should print the number and names of loaded calendars."""
        mock_genai_client.return_value = MagicMock()
        mock_get_service.return_value = MagicMock()
        mock_get_calendar_map.return_value = {
            "primary": "primary",
            "work": "work_id",
            "personal": "personal_id",
        }

        create_services(test_config)

        mock_print.assert_any_call("Loading calendars...")
        # Check that print was called with calendar info
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Loaded 3 calendars" in call for call in print_calls)
