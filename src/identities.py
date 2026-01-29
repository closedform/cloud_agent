"""Identity management for known users.

Maps email addresses to user identities with names for personalization.
"""

from dataclasses import dataclass

from src.utils import normalize_email


@dataclass(frozen=True)
class Identity:
    """Represents a known user identity."""

    email: str
    name: str
    short_name: str


# Registry of known identities, keyed by normalized (lowercase) email
IDENTITIES: dict[str, Identity] = {
    "dinunnob@gmail.com": Identity(
        email="dinunnob@gmail.com",
        name="Brandon DiNunno",
        short_name="Brandon",
    ),
    "slr.dinunno@gmail.com": Identity(
        email="slr.dinunno@gmail.com",
        name="Samantha DiNunno",
        short_name="Samantha",
    ),
}


def get_identity(email: str) -> Identity | None:
    """Get identity for an email address, or None if unknown.

    Args:
        email: Email address to look up. Case-insensitive matching is used.

    Returns:
        Identity object if found, None if the email is not in the registry.
    """
    normalized = normalize_email(email)
    return IDENTITIES.get(normalized)
