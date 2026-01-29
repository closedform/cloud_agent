"""Tests for src/config.py"""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Config, _get_project_root, _parse_int_env, _validate_timezone, get_config


class TestParseIntEnv:
    """Tests for _parse_int_env helper function."""

    def test_returns_default_when_not_set(self):
        """Should return default when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert _parse_int_env("NONEXISTENT_VAR", 42) == 42

    def test_parses_valid_integer(self):
        """Should parse valid integer string."""
        with patch.dict(os.environ, {"TEST_INT": "123"}, clear=True):
            assert _parse_int_env("TEST_INT", 0) == 123

    def test_returns_default_for_invalid_integer(self):
        """Should return default when value is not a valid integer."""
        with patch.dict(os.environ, {"TEST_INT": "not_a_number"}, clear=True):
            assert _parse_int_env("TEST_INT", 99) == 99

    def test_returns_default_for_empty_string(self):
        """Should return default for empty string."""
        with patch.dict(os.environ, {"TEST_INT": ""}, clear=True):
            assert _parse_int_env("TEST_INT", 50) == 50

    def test_handles_negative_integers(self):
        """Should handle negative integers."""
        with patch.dict(os.environ, {"TEST_INT": "-10"}, clear=True):
            assert _parse_int_env("TEST_INT", 0) == -10

    def test_handles_float_string(self):
        """Should return default for float strings (not valid int)."""
        with patch.dict(os.environ, {"TEST_INT": "3.14"}, clear=True):
            assert _parse_int_env("TEST_INT", 0) == 0


class TestValidateTimezone:
    """Tests for _validate_timezone helper function."""

    def test_valid_timezone_returned(self):
        """Should return valid timezone string as-is."""
        assert _validate_timezone("America/New_York") == "America/New_York"
        assert _validate_timezone("Europe/London") == "Europe/London"
        assert _validate_timezone("UTC") == "UTC"

    def test_invalid_timezone_returns_default(self):
        """Should return default for invalid timezone."""
        assert _validate_timezone("Invalid/Timezone") == "America/New_York"
        assert _validate_timezone("Not_A_Timezone") == "America/New_York"

    def test_custom_default(self):
        """Should use custom default when provided."""
        assert _validate_timezone("Invalid/TZ", "UTC") == "UTC"

    def test_empty_string_returns_default(self):
        """Should return default for empty string."""
        assert _validate_timezone("") == "America/New_York"


class TestConfig:
    """Tests for the Config dataclass."""

    def test_config_is_frozen(self):
        """Config should be immutable (frozen dataclass)."""
        config = Config(
            gemini_api_key="test-key",
            gemini_model="test-model",
            gemini_research_model="test-research",
            email_user="test@example.com",
            email_pass="password",
            allowed_senders=("sender@example.com",),
            admin_emails=("admin@example.com",),
            poll_interval=60,
            imap_server="imap.test.com",
            smtp_server="smtp.test.com",
            smtp_port=587,
            project_root=Path("/tmp/test"),
            input_dir=Path("/tmp/test/inputs"),
            processed_dir=Path("/tmp/test/processed"),
            failed_dir=Path("/tmp/test/failed"),
            reminders_file=Path("/tmp/test/reminders.json"),
            reminder_log_file=Path("/tmp/test/reminder_log.json"),
            user_data_file=Path("/tmp/test/user_data.json"),
            rules_file=Path("/tmp/test/rules.json"),
            diary_file=Path("/tmp/test/diary.json"),
            triggered_file=Path("/tmp/test/triggered.json"),
            sessions_file=Path("/tmp/test/sessions.json"),
            token_path=Path("/tmp/test/token.json"),
            credentials_path=Path("/tmp/test/credentials.json"),
            max_task_retries=3,
            timezone="America/New_York",
            default_calendar="primary",
        )
        with pytest.raises(FrozenInstanceError):
            config.gemini_api_key = "modified"

    def test_cannot_modify_any_field(self):
        """Should not be able to modify any field on Config."""
        config = Config(
            gemini_api_key="key",
            gemini_model="model",
            gemini_research_model="research",
            email_user="user@test.com",
            email_pass="pass",
            allowed_senders=(),
            admin_emails=(),
            poll_interval=30,
            imap_server="imap.test.com",
            smtp_server="smtp.test.com",
            smtp_port=587,
            project_root=Path("/tmp"),
            input_dir=Path("/tmp/inputs"),
            processed_dir=Path("/tmp/processed"),
            failed_dir=Path("/tmp/failed"),
            reminders_file=Path("/tmp/reminders.json"),
            reminder_log_file=Path("/tmp/reminder_log.json"),
            user_data_file=Path("/tmp/user_data.json"),
            rules_file=Path("/tmp/rules.json"),
            diary_file=Path("/tmp/diary.json"),
            triggered_file=Path("/tmp/triggered.json"),
            sessions_file=Path("/tmp/sessions.json"),
            token_path=Path("/tmp/token.json"),
            credentials_path=Path("/tmp/credentials.json"),
            max_task_retries=3,
            timezone="UTC",
            default_calendar="primary",
        )
        # Test several fields to ensure all are frozen
        with pytest.raises(FrozenInstanceError):
            config.email_user = "new@test.com"
        with pytest.raises(FrozenInstanceError):
            config.poll_interval = 120
        with pytest.raises(FrozenInstanceError):
            config.timezone = "Europe/London"

    def test_config_equality(self):
        """Two configs with same values should be equal."""
        kwargs = {
            "gemini_api_key": "key",
            "gemini_model": "model",
            "gemini_research_model": "research",
            "email_user": "user@test.com",
            "email_pass": "pass",
            "allowed_senders": ("a@b.com",),
            "admin_emails": (),
            "poll_interval": 60,
            "imap_server": "imap.test.com",
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "project_root": Path("/tmp"),
            "input_dir": Path("/tmp/inputs"),
            "processed_dir": Path("/tmp/processed"),
            "failed_dir": Path("/tmp/failed"),
            "reminders_file": Path("/tmp/reminders.json"),
            "reminder_log_file": Path("/tmp/reminder_log.json"),
            "user_data_file": Path("/tmp/user_data.json"),
            "rules_file": Path("/tmp/rules.json"),
            "diary_file": Path("/tmp/diary.json"),
            "triggered_file": Path("/tmp/triggered.json"),
            "sessions_file": Path("/tmp/sessions.json"),
            "token_path": Path("/tmp/token.json"),
            "credentials_path": Path("/tmp/credentials.json"),
            "max_task_retries": 3,
            "timezone": "America/New_York",
            "default_calendar": "primary",
        }
        config1 = Config(**kwargs)
        config2 = Config(**kwargs)
        assert config1 == config2


class TestGetProjectRoot:
    """Tests for _get_project_root function."""

    def test_finds_project_root(self):
        """Should find the project root containing pyproject.toml."""
        root = _get_project_root()
        assert root.exists()
        assert (root / "pyproject.toml").exists()

    def test_returns_path_object(self):
        """Should return a Path object."""
        root = _get_project_root()
        assert isinstance(root, Path)

    def test_root_contains_src_directory(self):
        """Project root should contain src directory."""
        root = _get_project_root()
        assert (root / "src").exists()
        assert (root / "src").is_dir()


class TestGetConfig:
    """Tests for get_config function."""

    def test_returns_config_instance(self):
        """Should return a Config instance."""
        # Clear cache to ensure fresh config
        get_config.cache_clear()
        config = get_config()
        assert isinstance(config, Config)

    def test_config_is_frozen_dataclass(self):
        """Config from get_config should be immutable."""
        get_config.cache_clear()
        config = get_config()
        with pytest.raises(FrozenInstanceError):
            config.gemini_model = "modified"

    def test_caching_returns_same_instance(self):
        """get_config should return the same cached instance."""
        get_config.cache_clear()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_cache_clear_creates_new_instance(self):
        """Clearing cache should create a new instance on next call."""
        get_config.cache_clear()
        config1 = get_config()
        get_config.cache_clear()
        config2 = get_config()
        # New instance but equal values (assuming same env)
        assert config1 == config2
        # After clearing, we got a fresh instance (may or may not be same object)
        # The key behavior is that cache_clear works without error


class TestGetConfigDefaults:
    """Tests for default values in get_config."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_default_gemini_model(self):
        """Default gemini_model should be gemini-3-flash-preview."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_model == "gemini-3-flash-preview"

    def test_default_gemini_research_model(self):
        """Default gemini_research_model should be gemini-2.5-flash."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_research_model == "gemini-2.5-flash"

    def test_default_poll_interval(self):
        """Default poll_interval should be 60."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.poll_interval == 60

    def test_default_imap_server(self):
        """Default imap_server should be imap.gmail.com."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.imap_server == "imap.gmail.com"

    def test_default_smtp_server(self):
        """Default smtp_server should be smtp.gmail.com."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.smtp_server == "smtp.gmail.com"

    def test_default_smtp_port(self):
        """Default smtp_port should be 587."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.smtp_port == 587

    def test_default_max_task_retries(self):
        """Default max_task_retries should be 3."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.max_task_retries == 3

    def test_default_timezone(self):
        """Default timezone should be America/New_York."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.timezone == "America/New_York"

    def test_default_calendar(self):
        """Default default_calendar should be primary."""
        with patch.dict(os.environ, {}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.default_calendar == "primary"

    def test_default_empty_allowed_senders(self):
        """Default allowed_senders should be empty tuple when no .env file."""
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == ()

    def test_default_empty_api_key(self):
        """Default gemini_api_key should be empty string when no .env file."""
        with patch.dict(os.environ, {}, clear=True), patch("src.config.load_dotenv"):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_api_key == ""


class TestGetConfigEnvironmentOverrides:
    """Tests for environment variable overrides."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_override_gemini_api_key(self):
        """GEMINI_API_KEY env var should override default."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key-123"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_api_key == "test-api-key-123"

    def test_override_gemini_model(self):
        """GEMINI_MODEL env var should override default."""
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-pro"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_model == "gemini-pro"

    def test_override_gemini_research_model(self):
        """GEMINI_RESEARCH_MODEL env var should override default."""
        with patch.dict(os.environ, {"GEMINI_RESEARCH_MODEL": "gemini-2.0-flash"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_research_model == "gemini-2.0-flash"

    def test_override_email_user(self):
        """EMAIL_USER env var should override default."""
        with patch.dict(os.environ, {"EMAIL_USER": "myemail@example.com"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.email_user == "myemail@example.com"

    def test_override_email_pass(self):
        """EMAIL_PASS env var should override default."""
        with patch.dict(os.environ, {"EMAIL_PASS": "secret123"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.email_pass == "secret123"

    def test_override_poll_interval(self):
        """POLL_INTERVAL env var should override default."""
        with patch.dict(os.environ, {"POLL_INTERVAL": "120"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.poll_interval == 120

    def test_override_imap_server(self):
        """IMAP_SERVER env var should override default."""
        with patch.dict(os.environ, {"IMAP_SERVER": "imap.custom.com"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.imap_server == "imap.custom.com"

    def test_override_smtp_server(self):
        """SMTP_SERVER env var should override default."""
        with patch.dict(os.environ, {"SMTP_SERVER": "smtp.custom.com"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.smtp_server == "smtp.custom.com"

    def test_override_smtp_port(self):
        """SMTP_PORT env var should override default."""
        with patch.dict(os.environ, {"SMTP_PORT": "465"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.smtp_port == 465

    def test_override_max_task_retries(self):
        """MAX_TASK_RETRIES env var should override default."""
        with patch.dict(os.environ, {"MAX_TASK_RETRIES": "5"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.max_task_retries == 5

    def test_override_timezone(self):
        """TIMEZONE env var should override default."""
        with patch.dict(os.environ, {"TIMEZONE": "Europe/London"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.timezone == "Europe/London"

    def test_override_default_calendar(self):
        """DEFAULT_CALENDAR env var should override default."""
        with patch.dict(os.environ, {"DEFAULT_CALENDAR": "work"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.default_calendar == "work"


class TestAllowedSendersParsing:
    """Tests for ALLOWED_SENDERS parsing."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_single_sender(self):
        """Should parse single allowed sender."""
        with patch.dict(os.environ, {"ALLOWED_SENDERS": "user@example.com"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == ("user@example.com",)

    def test_multiple_senders(self):
        """Should parse multiple comma-separated senders."""
        senders = "user1@example.com,user2@example.com,user3@example.com"
        with patch.dict(os.environ, {"ALLOWED_SENDERS": senders}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == (
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            )

    def test_senders_with_whitespace(self):
        """Should strip whitespace from sender emails."""
        senders = "  user1@example.com , user2@example.com  ,  user3@example.com  "
        with patch.dict(os.environ, {"ALLOWED_SENDERS": senders}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == (
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            )

    def test_empty_senders_string(self):
        """Empty string should result in empty tuple."""
        with patch.dict(os.environ, {"ALLOWED_SENDERS": ""}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == ()

    def test_senders_with_empty_entries(self):
        """Should filter out empty entries from commas."""
        senders = "user1@example.com,,user2@example.com,"
        with patch.dict(os.environ, {"ALLOWED_SENDERS": senders}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.allowed_senders == ("user1@example.com", "user2@example.com")

    def test_allowed_senders_is_tuple(self):
        """allowed_senders should be a tuple, not a list."""
        senders = "user@example.com"
        with patch.dict(os.environ, {"ALLOWED_SENDERS": senders}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert isinstance(config.allowed_senders, tuple)


class TestPathConstruction:
    """Tests for path construction in config."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_paths_are_path_objects(self):
        """All path fields should be Path objects."""
        config = get_config()
        assert isinstance(config.project_root, Path)
        assert isinstance(config.input_dir, Path)
        assert isinstance(config.processed_dir, Path)
        assert isinstance(config.failed_dir, Path)
        assert isinstance(config.reminders_file, Path)
        assert isinstance(config.reminder_log_file, Path)
        assert isinstance(config.user_data_file, Path)
        assert isinstance(config.rules_file, Path)
        assert isinstance(config.diary_file, Path)
        assert isinstance(config.triggered_file, Path)
        assert isinstance(config.sessions_file, Path)
        assert isinstance(config.token_path, Path)
        assert isinstance(config.credentials_path, Path)

    def test_paths_anchored_to_project_root(self):
        """All paths should be under project_root."""
        config = get_config()
        root = config.project_root
        assert config.input_dir == root / "inputs"
        assert config.processed_dir == root / "processed"
        assert config.failed_dir == root / "failed"
        assert config.reminders_file == root / "reminders.json"
        assert config.reminder_log_file == root / "reminder_log.json"
        assert config.user_data_file == root / "user_data.json"
        assert config.rules_file == root / "rules.json"
        assert config.diary_file == root / "diary.json"
        assert config.triggered_file == root / "triggered.json"
        assert config.sessions_file == root / "sessions.json"
        assert config.token_path == root / "token.json"
        assert config.credentials_path == root / "credentials.json"

    def test_project_root_is_absolute(self):
        """project_root should be an absolute path."""
        config = get_config()
        assert config.project_root.is_absolute()


class TestConfigIntegration:
    """Integration tests for config behavior."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_multiple_env_overrides(self):
        """Should handle multiple environment overrides simultaneously."""
        env = {
            "GEMINI_API_KEY": "multi-test-key",
            "GEMINI_MODEL": "gemini-ultra",
            "EMAIL_USER": "multi@test.com",
            "POLL_INTERVAL": "30",
            "TIMEZONE": "UTC",
            "ALLOWED_SENDERS": "a@b.com,c@d.com",
        }
        with patch.dict(os.environ, env, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.gemini_api_key == "multi-test-key"
            assert config.gemini_model == "gemini-ultra"
            assert config.email_user == "multi@test.com"
            assert config.poll_interval == 30
            assert config.timezone == "UTC"
            assert config.allowed_senders == ("a@b.com", "c@d.com")

    def test_config_hashable(self):
        """Frozen dataclass should be hashable."""
        config = get_config()
        # Should not raise - frozen dataclasses are hashable
        hash(config)

    def test_config_can_be_used_in_set(self):
        """Config should be usable in sets (requires hashability)."""
        config1 = get_config()
        config_set = {config1}
        assert config1 in config_set


class TestConfigRobustness:
    """Tests for config robustness with invalid environment values."""

    @pytest.fixture(autouse=True)
    def clear_config_cache(self):
        """Clear config cache before and after each test."""
        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_invalid_poll_interval_uses_default(self):
        """Invalid POLL_INTERVAL should fall back to default."""
        with patch.dict(os.environ, {"POLL_INTERVAL": "not_a_number"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.poll_interval == 60  # default

    def test_invalid_smtp_port_uses_default(self):
        """Invalid SMTP_PORT should fall back to default."""
        with patch.dict(os.environ, {"SMTP_PORT": "abc"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.smtp_port == 587  # default

    def test_invalid_max_task_retries_uses_default(self):
        """Invalid MAX_TASK_RETRIES should fall back to default."""
        with patch.dict(os.environ, {"MAX_TASK_RETRIES": "many"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.max_task_retries == 3  # default

    def test_invalid_timezone_uses_default(self):
        """Invalid TIMEZONE should fall back to default."""
        with patch.dict(os.environ, {"TIMEZONE": "Invalid/NotATimezone"}, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.timezone == "America/New_York"  # default

    def test_empty_integer_values_use_defaults(self):
        """Empty integer env vars should fall back to defaults."""
        env = {
            "POLL_INTERVAL": "",
            "SMTP_PORT": "",
            "MAX_TASK_RETRIES": "",
        }
        with patch.dict(os.environ, env, clear=True):
            get_config.cache_clear()
            config = get_config()
            assert config.poll_interval == 60
            assert config.smtp_port == 587
            assert config.max_task_retries == 3
