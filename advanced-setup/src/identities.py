"""Identity management for known users.

Maps email addresses to user identities with names for personalization.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    """Represents a known user identity."""

    email: str
    name: str
    short_name: str


# Add your known users here for personalized responses
# Example:
# IDENTITIES: dict[str, Identity] = {
#     "user@example.com": Identity(
#         email="user@example.com",
#         name="John Doe",
#         short_name="John",
#     ),
# }

IDENTITIES: dict[str, Identity] = {}


def get_identity(email: str) -> Identity | None:
    """Get identity for an email address, or None if unknown."""
    return IDENTITIES.get(email)
