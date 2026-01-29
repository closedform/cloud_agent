"""Stress tests for configuration handling.

Tests edge cases and error conditions in config.py:
- Missing required environment variables
- Invalid values (non-numeric port, invalid timezone)
- Empty allowed_senders
- Path traversal in file paths
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

from src.config import Config, get_config


class TestMissingRequiredEnvVars:
    """Test behavior when required environment variables are missing."""

    def test_missing_gemini_api_key_returns_empty_string(self):
        """BUG: Missing GEMINI_API_KEY silently returns empty string instead of raising."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # This should probably raise an error, but it returns empty string
                assert config.gemini_api_key == ""

    def test_missing_email_user_returns_empty_string(self):
        """BUG: Missing EMAIL_USER silently returns empty string instead of raising."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # This should probably raise an error, but it returns empty string
                assert config.email_user == ""

    def test_missing_email_pass_returns_empty_string(self):
        """BUG: Missing EMAIL_PASS silently returns empty string instead of raising."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # This should probably raise an error, but it returns empty string
                assert config.email_pass == ""

    def test_all_required_vars_missing_still_creates_config(self):
        """BUG: Config is created successfully even with all critical vars missing."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # All these critical values are empty but no error raised
                assert config.gemini_api_key == ""
                assert config.email_user == ""
                assert config.email_pass == ""
                assert config.allowed_senders == ()


class TestInvalidNumericValues:
    """Test behavior with invalid numeric values for port, interval, etc. - FIXED."""

    def test_non_numeric_poll_interval_uses_default(self):
        """FIXED: Non-numeric POLL_INTERVAL now falls back to default."""
        get_config.cache_clear()
        env = {"POLL_INTERVAL": "invalid"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.poll_interval == 60  # default

    def test_non_numeric_smtp_port_uses_default(self):
        """FIXED: Non-numeric SMTP_PORT now falls back to default."""
        get_config.cache_clear()
        env = {"SMTP_PORT": "not_a_port"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.smtp_port == 587  # default

    def test_non_numeric_max_task_retries_uses_default(self):
        """FIXED: Non-numeric MAX_TASK_RETRIES now falls back to default."""
        get_config.cache_clear()
        env = {"MAX_TASK_RETRIES": "three"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.max_task_retries == 3  # default

    def test_negative_poll_interval_accepted(self):
        """BUG: Negative POLL_INTERVAL is accepted without validation."""
        get_config.cache_clear()
        env = {"POLL_INTERVAL": "-10"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Negative interval doesn't make sense but is accepted
                assert config.poll_interval == -10

    def test_zero_poll_interval_accepted(self):
        """BUG: Zero POLL_INTERVAL is accepted without validation."""
        get_config.cache_clear()
        env = {"POLL_INTERVAL": "0"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Zero interval could cause infinite loops
                assert config.poll_interval == 0

    def test_negative_smtp_port_accepted(self):
        """BUG: Negative SMTP_PORT is accepted without validation."""
        get_config.cache_clear()
        env = {"SMTP_PORT": "-1"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Negative port doesn't make sense but is accepted
                assert config.smtp_port == -1

    def test_smtp_port_out_of_valid_range(self):
        """BUG: SMTP_PORT above 65535 is accepted without validation."""
        get_config.cache_clear()
        env = {"SMTP_PORT": "99999"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Port above valid range (0-65535) is accepted
                assert config.smtp_port == 99999

    def test_float_poll_interval_uses_default(self):
        """FIXED: Float POLL_INTERVAL now falls back to default."""
        get_config.cache_clear()
        env = {"POLL_INTERVAL": "60.9"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                # Float string is not a valid int, so falls back to default
                config = get_config()
                assert config.poll_interval == 60  # default


class TestInvalidTimezone:
    """Test behavior with invalid timezone values - all now FIXED."""

    def test_invalid_timezone_falls_back_to_default(self):
        """FIXED: Invalid TIMEZONE value now falls back to default."""
        get_config.cache_clear()
        env = {"TIMEZONE": "Invalid/Timezone"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Invalid timezone now falls back to default
                assert config.timezone == "America/New_York"
                # Verify the default is valid
                pytz.timezone(config.timezone)

    def test_empty_timezone_uses_default(self):
        """FIXED: Empty TIMEZONE now falls back to default."""
        get_config.cache_clear()
        env = {"TIMEZONE": ""}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Empty string now falls back to default
                assert config.timezone == "America/New_York"
                # Verify the default is valid
                pytz.timezone(config.timezone)

    def test_timezone_with_typo_falls_back_to_default(self):
        """FIXED: Common timezone typo now falls back to default."""
        get_config.cache_clear()
        env = {"TIMEZONE": "America/NewYork"}  # Missing underscore
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Invalid timezone now falls back to default instead of failing at runtime
                assert config.timezone == "America/New_York"
                # This should no longer raise - the timezone is now valid
                pytz.timezone(config.timezone)


class TestEmptyAllowedSenders:
    """Test behavior with empty or malformed allowed_senders."""

    def test_empty_allowed_senders_env_returns_empty_tuple(self):
        """Empty ALLOWED_SENDERS returns empty tuple."""
        get_config.cache_clear()
        env = {"ALLOWED_SENDERS": ""}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.allowed_senders == ()

    def test_missing_allowed_senders_env_returns_empty_tuple(self):
        """BUG: Missing ALLOWED_SENDERS returns empty tuple - no one can send emails."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # This means no one is allowed to send - is this intentional?
                assert config.allowed_senders == ()

    def test_allowed_senders_with_only_commas(self):
        """ALLOWED_SENDERS with only commas returns empty tuple."""
        get_config.cache_clear()
        env = {"ALLOWED_SENDERS": ",,,"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.allowed_senders == ()

    def test_allowed_senders_with_whitespace_entries(self):
        """ALLOWED_SENDERS with whitespace entries are filtered out."""
        get_config.cache_clear()
        env = {"ALLOWED_SENDERS": "  ,  ,user@example.com,  "}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.allowed_senders == ("user@example.com",)

    def test_allowed_senders_not_validated_as_emails(self):
        """BUG: ALLOWED_SENDERS entries are not validated as email addresses."""
        get_config.cache_clear()
        env = {"ALLOWED_SENDERS": "not_an_email,@invalid,user@,@"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Invalid emails are accepted
                assert config.allowed_senders == ("not_an_email", "@invalid", "user@", "@")


class TestPathTraversal:
    """Test behavior with path traversal attempts in file paths."""

    def test_paths_are_anchored_to_project_root(self):
        """Paths are correctly anchored to project root."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # All paths should be under project_root
                assert config.input_dir.is_relative_to(config.project_root)
                assert config.processed_dir.is_relative_to(config.project_root)
                assert config.reminders_file.is_relative_to(config.project_root)

    def test_path_traversal_not_possible_via_env(self):
        """File paths are hardcoded and not configurable via environment."""
        get_config.cache_clear()
        # There's no env var to override file paths, so path traversal
        # via environment is not possible for file paths
        # This is actually good security practice
        env = {"INPUT_DIR": "/etc/passwd"}  # This should have no effect
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # INPUT_DIR env var is ignored - paths are hardcoded
                assert config.input_dir == config.project_root / "inputs"
                assert str(config.input_dir) != "/etc/passwd"

    def test_project_root_detection_goes_up_directory_tree(self):
        """_get_project_root walks up directory tree looking for pyproject.toml."""
        # This is expected behavior, but worth documenting
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Verify project root contains pyproject.toml
                assert (config.project_root / "pyproject.toml").exists()


class TestConfigImmutability:
    """Test that Config is truly immutable."""

    def test_config_is_frozen(self):
        """Config dataclass is frozen and cannot be modified."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                with pytest.raises(AttributeError):
                    config.gemini_api_key = "new_key"

    def test_config_is_cached(self):
        """get_config returns the same cached instance."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config1 = get_config()
                config2 = get_config()
                assert config1 is config2


class TestEdgeCases:
    """Test various edge cases in configuration."""

    def test_unicode_in_allowed_senders(self):
        """Unicode characters in email addresses are accepted."""
        get_config.cache_clear()
        env = {"ALLOWED_SENDERS": "user@example.com"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.allowed_senders == ("user@example.com",)

    def test_very_long_allowed_senders_list(self):
        """Very long ALLOWED_SENDERS list is accepted."""
        get_config.cache_clear()
        emails = ",".join(f"user{i}@example.com" for i in range(1000))
        env = {"ALLOWED_SENDERS": emails}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert len(config.allowed_senders) == 1000

    def test_default_model_values(self):
        """Default model values are set when env vars missing."""
        get_config.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                assert config.gemini_model == "gemini-3-flash-preview"
                assert config.gemini_research_model == "gemini-2.5-flash"

    def test_whitespace_in_env_var_values_preserved(self):
        """Leading/trailing whitespace in env vars is NOT stripped for most values."""
        get_config.cache_clear()
        env = {"GEMINI_API_KEY": "  key_with_spaces  "}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # BUG: Whitespace is preserved, which could cause API failures
                assert config.gemini_api_key == "  key_with_spaces  "

    def test_newline_in_env_var_values_preserved(self):
        """BUG: Newlines in env var values are preserved."""
        get_config.cache_clear()
        env = {"EMAIL_USER": "user@example.com\n"}
        with patch.dict(os.environ, env, clear=True):
            with patch("src.config.load_dotenv"):
                config = get_config()
                # Newline is preserved, which could cause issues
                assert config.email_user == "user@example.com\n"
