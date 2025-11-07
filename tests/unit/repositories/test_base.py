"""Unit tests for base repository utilities."""

from uuid import UUID, uuid7

import pytest

from crawler.db.repositories.base import to_uuid, to_uuid_optional


class TestToUuid:
    """Tests for to_uuid helper function."""

    def test_converts_string_to_uuid(self) -> None:
        """Test that string is converted to UUID."""
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = to_uuid(uuid_str)

        assert isinstance(result, UUID)
        assert str(result) == uuid_str

    def test_returns_uuid_unchanged(self) -> None:
        """Test that UUID is returned unchanged."""
        original_uuid = uuid7()
        result = to_uuid(original_uuid)

        assert result is original_uuid
        assert isinstance(result, UUID)

    def test_raises_on_invalid_string(self) -> None:
        """Test that invalid UUID string raises ValueError."""
        with pytest.raises(ValueError):
            to_uuid("not-a-valid-uuid")

    def test_handles_different_uuid_formats(self) -> None:
        """Test that different UUID string formats are accepted."""
        # With hyphens
        uuid_with_hyphens = "550e8400-e29b-41d4-a716-446655440000"
        result1 = to_uuid(uuid_with_hyphens)
        assert isinstance(result1, UUID)

        # Without hyphens
        uuid_without_hyphens = "550e8400e29b41d4a716446655440000"
        result2 = to_uuid(uuid_without_hyphens)
        assert isinstance(result2, UUID)

        # Verify they're equal
        assert result1 == result2


class TestToUuidOptional:
    """Tests for to_uuid_optional helper function."""

    def test_converts_string_to_uuid(self) -> None:
        """Test that string is converted to UUID."""
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = to_uuid_optional(uuid_str)

        assert isinstance(result, UUID)
        assert str(result) == uuid_str

    def test_returns_uuid_unchanged(self) -> None:
        """Test that UUID is returned unchanged."""
        original_uuid = uuid7()
        result = to_uuid_optional(original_uuid)

        assert result is original_uuid
        assert isinstance(result, UUID)

    def test_returns_none_for_none(self) -> None:
        """Test that None is returned unchanged."""
        result = to_uuid_optional(None)
        assert result is None

    def test_raises_on_invalid_string(self) -> None:
        """Test that invalid UUID string raises ValueError."""
        with pytest.raises(ValueError):
            to_uuid_optional("not-a-valid-uuid")

    def test_handles_different_uuid_formats(self) -> None:
        """Test that different UUID string formats are accepted."""
        # With hyphens
        uuid_with_hyphens = "550e8400-e29b-41d4-a716-446655440000"
        result1 = to_uuid_optional(uuid_with_hyphens)
        assert isinstance(result1, UUID)

        # Without hyphens
        uuid_without_hyphens = "550e8400e29b41d4a716446655440000"
        result2 = to_uuid_optional(uuid_without_hyphens)
        assert isinstance(result2, UUID)

        # Verify they're equal
        assert result1 == result2
