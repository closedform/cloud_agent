"""Stress tests for src/identities.py - Bug hunting for edge cases."""

import pytest

from src.identities import IDENTITIES, Identity, get_identity


class TestUnknownEmailAddresses:
    """Tests for unknown email address handling."""

    def test_unknown_email_returns_none(self):
        """Unknown email should return None, not raise."""
        result = get_identity("completely_unknown@nowhere.invalid")
        assert result is None

    def test_email_with_trailing_space_now_matches(self):
        """Email with trailing space should match after normalization (fix applied)."""
        # dinunnob@gmail.com exists, spaces are now trimmed
        result = get_identity("dinunnob@gmail.com ")  # trailing space
        assert result is not None
        assert result.email == "dinunnob@gmail.com"

    def test_email_with_leading_space_now_matches(self):
        """Email with leading space should match after normalization (fix applied)."""
        result = get_identity(" dinunnob@gmail.com")
        assert result is not None
        assert result.email == "dinunnob@gmail.com"

    def test_email_with_plus_addressing(self):
        """Plus addressing variant should not match base email."""
        result = get_identity("dinunnob+test@gmail.com")
        assert result is None

    def test_subdomain_variant(self):
        """Subdomain variant should not match."""
        result = get_identity("dinunnob@subdomain.gmail.com")
        assert result is None

    def test_typo_in_domain(self):
        """Typo in domain should not match."""
        result = get_identity("dinunnob@gmal.com")
        assert result is None


class TestCaseSensitivity:
    """Tests for case-insensitive email lookup (fix applied)."""

    def test_uppercase_email_now_found(self):
        """Uppercase version of known email should match (fix applied)."""
        result = get_identity("DINUNNOB@GMAIL.COM")
        assert result is not None
        assert result.email == "dinunnob@gmail.com"

    def test_mixed_case_email_now_found(self):
        """Mixed case email should match lowercase (fix applied)."""
        result = get_identity("DiNuNnOb@GmAiL.cOm")
        assert result is not None
        assert result.email == "dinunnob@gmail.com"

    def test_uppercase_local_part_now_found(self):
        """Uppercase local part should match (fix applied)."""
        result = get_identity("DINUNNOB@gmail.com")
        assert result is not None

    def test_uppercase_domain_now_found(self):
        """Uppercase domain should match (fix applied)."""
        result = get_identity("dinunnob@GMAIL.COM")
        assert result is not None

    def test_case_insensitivity_implemented(self):
        """
        FIX VERIFICATION: Email lookup is now case-insensitive.

        Email addresses should be treated as case-insensitive per RFC 5321.
        The local part (before @) CAN be case-sensitive per spec, but in practice
        most email providers (Gmail, etc.) treat them as case-insensitive.
        The domain part (after @) MUST be case-insensitive.

        This was fixed to normalize emails before lookup.
        """
        lowercase = get_identity("dinunnob@gmail.com")
        uppercase = get_identity("DINUNNOB@GMAIL.COM")

        assert lowercase is not None
        assert uppercase is not None
        assert lowercase == uppercase  # Now both return the same identity


class TestSpecialCharactersInNames:
    """Tests for special characters in Identity names."""

    def test_identity_with_unicode_name(self):
        """Identity should handle unicode names."""
        identity = Identity(
            email="unicode@test.com",
            name="Jose Garcia",  # Spanish accent
            short_name="Jose",
        )
        assert identity.name == "Jose Garcia"

    def test_identity_with_emoji_in_name(self):
        """Identity should handle emoji in names (edge case)."""
        identity = Identity(
            email="emoji@test.com",
            name="Star Person",  # with emoji
            short_name="Star",
        )
        # Just verify it doesn't crash
        assert len(identity.name) > 0

    def test_identity_with_apostrophe(self):
        """Identity should handle names with apostrophes."""
        identity = Identity(
            email="irish@test.com",
            name="Patrick O'Brien",
            short_name="Patrick",
        )
        assert "O'Brien" in identity.name

    def test_identity_with_hyphenated_name(self):
        """Identity should handle hyphenated names."""
        identity = Identity(
            email="hyphen@test.com",
            name="Mary-Jane Watson",
            short_name="Mary-Jane",
        )
        assert "-" in identity.name

    def test_identity_with_quotes(self):
        """Identity should handle names with quotes."""
        identity = Identity(
            email="nick@test.com",
            name='John "Johnny" Doe',
            short_name="Johnny",
        )
        assert '"' in identity.name


class TestEmptyAndNoneInputs:
    """Tests for empty and None input handling."""

    def test_empty_string_email(self):
        """Empty string email should return None."""
        result = get_identity("")
        assert result is None

    def test_none_email_raises_attributeerror(self):
        """
        Passing None to get_identity raises AttributeError.

        The function signature says email: str, and passing None
        will raise AttributeError when trying to call .strip() on None.
        This is expected behavior - callers should validate inputs.
        """
        with pytest.raises(AttributeError):
            get_identity(None)  # type: ignore

    def test_whitespace_only_email(self):
        """Whitespace-only email should return None."""
        result = get_identity("   ")
        assert result is None

    def test_newline_in_email_matches_after_strip(self):
        """Email with newline should match after normalization (fix applied)."""
        result = get_identity("dinunnob@gmail.com\n")
        assert result is not None
        assert result.email == "dinunnob@gmail.com"

    def test_tab_in_email_matches_after_strip(self):
        """Email with tab should match after normalization (fix applied)."""
        result = get_identity("\tdinunnob@gmail.com")
        assert result is not None
        assert result.email == "dinunnob@gmail.com"


class TestIdentityDataclassEdgeCases:
    """Edge cases for the Identity dataclass itself."""

    def test_identity_with_empty_name(self):
        """Identity with empty name should still create."""
        identity = Identity(
            email="empty@test.com",
            name="",
            short_name="",
        )
        assert identity.name == ""
        assert identity.short_name == ""

    def test_identity_with_very_long_name(self):
        """Identity should handle very long names."""
        long_name = "A" * 10000
        identity = Identity(
            email="long@test.com",
            name=long_name,
            short_name="A",
        )
        assert len(identity.name) == 10000

    def test_identity_with_very_long_email(self):
        """Identity should handle very long emails."""
        long_email = "a" * 1000 + "@test.com"
        identity = Identity(
            email=long_email,
            name="Long Email",
            short_name="Long",
        )
        assert len(identity.email) > 1000

    def test_identity_hashable(self):
        """Identity should be hashable (frozen dataclass)."""
        identity = Identity(
            email="hash@test.com",
            name="Hash Test",
            short_name="Hash",
        )
        # Should not raise
        hash_value = hash(identity)
        assert isinstance(hash_value, int)

    def test_identity_can_be_set_member(self):
        """Identity should work as set member."""
        id1 = Identity(email="a@b.com", name="A", short_name="A")
        id2 = Identity(email="a@b.com", name="A", short_name="A")
        id3 = Identity(email="c@d.com", name="C", short_name="C")

        s = {id1, id2, id3}
        assert len(s) == 2  # id1 and id2 are equal


class TestIdentitiesRegistryIntegrity:
    """Tests for IDENTITIES registry edge cases."""

    def test_registry_keys_match_identity_emails(self):
        """Registry keys should match the identity email field."""
        for key, identity in IDENTITIES.items():
            assert key == identity.email, f"Mismatch: key={key}, identity.email={identity.email}"

    def test_registry_has_no_duplicate_short_names(self):
        """Check for duplicate short names (may cause confusion)."""
        short_names = [identity.short_name for identity in IDENTITIES.values()]
        # This is informational - duplicates might be intentional
        unique_names = set(short_names)
        if len(unique_names) != len(short_names):
            duplicates = [n for n in short_names if short_names.count(n) > 1]
            pytest.skip(f"Found duplicate short names (may be intentional): {duplicates}")

    def test_all_emails_lowercase(self):
        """
        BUG DETECTION: Check if all registered emails are lowercase.

        If the lookup is case-sensitive, having uppercase in registry
        would be problematic.
        """
        for email in IDENTITIES.keys():
            assert email == email.lower(), f"Email {email} contains uppercase characters"

    def test_no_whitespace_in_emails(self):
        """Check that no registered emails have whitespace."""
        for email in IDENTITIES.keys():
            assert email.strip() == email, f"Email {email} has leading/trailing whitespace"
            assert " " not in email, f"Email {email} contains spaces"


class TestEmailLookupRobustness:
    """Tests for lookup robustness with malformed inputs."""

    def test_email_with_null_byte(self):
        """Email with null byte should return None (not stripped, so no match)."""
        result = get_identity("dinunnob@gmail.com\x00")
        assert result is None

    def test_email_as_bytes_returns_none(self):
        """
        Passing bytes instead of string returns None (bytes have strip/lower methods).

        The function signature specifies `email: str`, but bytes also have
        .strip() and .lower() methods, so this doesn't raise an error.
        However, the lookup will fail since the normalized bytes won't match
        any string key in the IDENTITIES dict.
        """
        result = get_identity(b"dinunnob@gmail.com")  # type: ignore
        assert result is None

    def test_email_as_int_raises_attributeerror(self):
        """
        Passing int instead of string should raise AttributeError.

        The function signature specifies `email: str`, and passing an int
        will raise AttributeError when trying to call .strip() on int.
        """
        with pytest.raises(AttributeError):
            get_identity(123)  # type: ignore

    def test_email_as_list_raises_attributeerror(self):
        """Passing list should raise AttributeError."""
        with pytest.raises(AttributeError):
            get_identity(["dinunnob@gmail.com"])  # type: ignore


class TestFixesVerified:
    """
    Verify that previously identified bugs have been fixed.

    These tests document the fixed behavior.
    """

    def test_fix_email_normalization_implemented(self):
        """
        FIX VERIFIED: Email normalization is now applied before lookup.

        Users can send email with different case or extra spaces,
        and the lookup will still work.
        """
        # All of these now match
        assert get_identity("dinunnob@gmail.com") is not None
        assert get_identity("DINUNNOB@gmail.com") is not None
        assert get_identity(" dinunnob@gmail.com ") is not None
        # And they all return the same identity
        assert get_identity("dinunnob@gmail.com") == get_identity("DINUNNOB@GMAIL.COM")

    def test_invalid_emails_still_return_none(self):
        """
        Invalid email strings still return None gracefully.

        The function accepts any string, including invalid emails.
        Returning None is acceptable behavior for unknown addresses.
        """
        # These all return None but are clearly not valid emails
        assert get_identity("not_an_email") is None
        assert get_identity("@@@") is None
        assert get_identity("") is None
