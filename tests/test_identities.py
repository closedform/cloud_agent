"""Tests for src/identities.py"""

import pytest

from src.identities import IDENTITIES, Identity, get_identity


class TestIdentity:
    """Tests for the Identity dataclass."""

    def test_identity_is_frozen(self):
        """Identity should be immutable."""
        identity = Identity(
            email="test@example.com",
            name="Test User",
            short_name="Test",
        )
        with pytest.raises(AttributeError):
            identity.name = "Modified"

    def test_identity_equality(self):
        """Two identities with same values should be equal."""
        id1 = Identity(email="a@b.com", name="A", short_name="A")
        id2 = Identity(email="a@b.com", name="A", short_name="A")
        assert id1 == id2


class TestGetIdentity:
    """Tests for get_identity function."""

    def test_returns_identity_for_known_email(self):
        """Should return Identity for registered email."""
        identity = get_identity("dinunnob@gmail.com")
        assert identity is not None
        assert identity.short_name == "Brandon"
        assert identity.name == "Brandon DiNunno"

    def test_returns_none_for_unknown_email(self):
        """Should return None for unregistered email."""
        identity = get_identity("unknown@example.com")
        assert identity is None

    def test_case_insensitive_lookup(self):
        """Email lookup should be case-insensitive."""
        identity = get_identity("DINUNNOB@GMAIL.COM")
        assert identity is not None
        assert identity.short_name == "Brandon"

    def test_whitespace_trimmed_lookup(self):
        """Email lookup should trim whitespace."""
        identity = get_identity("  dinunnob@gmail.com  ")
        assert identity is not None
        assert identity.short_name == "Brandon"


class TestIdentitiesRegistry:
    """Tests for the IDENTITIES registry."""

    def test_identities_not_empty(self):
        """IDENTITIES should have at least one entry."""
        assert len(IDENTITIES) > 0

    def test_all_identities_valid(self):
        """All entries should have required fields."""
        for email, identity in IDENTITIES.items():
            assert identity.email == email
            assert len(identity.name) > 0
            assert len(identity.short_name) > 0
