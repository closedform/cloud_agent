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

    def test_returns_none_for_unknown_email(self):
        """Should return None for unregistered email."""
        identity = get_identity("unknown@example.com")
        assert identity is None

    def test_case_sensitive_lookup(self):
        """Email lookup should be case-sensitive."""
        # Even if there were entries, uppercase wouldn't match
        identity = get_identity("TEST@EXAMPLE.COM")
        assert identity is None


class TestIdentitiesRegistry:
    """Tests for the IDENTITIES registry."""

    def test_identities_is_dict(self):
        """IDENTITIES should be a dictionary."""
        assert isinstance(IDENTITIES, dict)

    def test_all_identities_valid(self):
        """All entries should have required fields."""
        for email, identity in IDENTITIES.items():
            assert identity.email == email
            assert len(identity.name) > 0
            assert len(identity.short_name) > 0
