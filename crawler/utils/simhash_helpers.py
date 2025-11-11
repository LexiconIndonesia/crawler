"""Helper functions for Simhash integration with PostgreSQL.

PostgreSQL BIGINT is signed (-2^63 to 2^63-1), but Simhash fingerprints
are unsigned 64-bit integers (0 to 2^64-1). These helpers handle the conversion.
"""


def to_signed_int64(unsigned: int) -> int:
    """Convert unsigned 64-bit integer to signed for PostgreSQL BIGINT.

    PostgreSQL BIGINT is signed, so we need to convert unsigned 64-bit
    integers from Simhash to signed representation.

    Args:
        unsigned: Unsigned 64-bit integer (0 to 2^64-1)

    Returns:
        Signed 64-bit integer (-2^63 to 2^63-1)

    Example:
        >>> to_signed_int64(18446744073709551615)  # Max unsigned 64-bit
        -1
        >>> to_signed_int64(9223372036854775808)  # 2^63
        -9223372036854775808
    """
    # If the value is >= 2^63, convert to negative
    if unsigned >= (1 << 63):
        return unsigned - (1 << 64)
    return unsigned


def from_signed_int64(signed: int) -> int:
    """Convert signed 64-bit integer from PostgreSQL BIGINT to unsigned.

    Args:
        signed: Signed 64-bit integer (-2^63 to 2^63-1)

    Returns:
        Unsigned 64-bit integer (0 to 2^64-1)

    Example:
        >>> from_signed_int64(-1)
        18446744073709551615
        >>> from_signed_int64(-9223372036854775808)
        9223372036854775808
    """
    # If negative, convert to unsigned representation
    if signed < 0:
        return signed + (1 << 64)
    return signed
