"""Base utilities for repositories."""

from uuid import UUID


def to_uuid(value: str | UUID) -> UUID:
    """Convert string to UUID if needed.

    Args:
        value: String or UUID value

    Returns:
        UUID instance
    """
    if isinstance(value, UUID):
        return value
    return UUID(value)


def to_uuid_optional(value: str | UUID | None) -> UUID | None:
    """Convert string to UUID if needed, handling None.

    Args:
        value: String, UUID, or None value

    Returns:
        UUID instance or None
    """
    if value is None:
        return None
    return to_uuid(value)
