"""Tests for src/utils.py"""

import pytest

from src.utils import normalize_email


class TestNormalizeEmail:
    """Tests for email normalization function."""

    def test_lowercase_conversion(self):
        """Should convert email to lowercase."""
        assert normalize_email("User@Example.COM") == "user@example.com"
        assert normalize_email("DINUNNOB@GMAIL.COM") == "dinunnob@gmail.com"

    def test_whitespace_stripping(self):
        """Should strip leading and trailing whitespace."""
        assert normalize_email("  user@example.com  ") == "user@example.com"
        assert normalize_email("\tuser@example.com\n") == "user@example.com"

    def test_combined_normalization(self):
        """Should handle both case and whitespace together."""
        assert normalize_email("  USER@EXAMPLE.COM  ") == "user@example.com"

    def test_already_normalized(self):
        """Should return identical string if already normalized."""
        email = "user@example.com"
        assert normalize_email(email) == email

    def test_empty_string(self):
        """Should handle empty string."""
        assert normalize_email("") == ""

    def test_whitespace_only(self):
        """Should return empty string for whitespace only."""
        assert normalize_email("   ") == ""

    def test_unicode_email(self):
        """Should handle unicode in email addresses."""
        # IDN emails with unicode
        assert normalize_email("user@example.com") == "user@example.com"
