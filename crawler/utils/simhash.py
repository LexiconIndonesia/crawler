"""Simhash implementation for fuzzy content matching.

Simhash is a locality-sensitive hashing algorithm that maps similar content
to similar hash values. It's particularly useful for near-duplicate detection
in web crawling.

Algorithm:
1. Tokenize text into features (words, n-grams, etc.)
2. Hash each feature to get a 64-bit hash
3. For each hash, add its bits to a vector (increment for 1, decrement for 0)
4. Convert vector to final fingerprint (positive -> 1, negative -> 0)
5. Use Hamming distance to compare fingerprints

References:
- Charikar, M. S. (2002). Similarity estimation techniques from rounding algorithms.
- https://en.wikipedia.org/wiki/SimHash
"""

import hashlib
import re
from collections.abc import Iterable


class Simhash:
    """Simhash implementation for fuzzy content matching.

    Generates a 64-bit fingerprint from text content that can be used for
    near-duplicate detection. Similar content produces similar fingerprints,
    measurable via Hamming distance.

    Example:
        >>> sh1 = Simhash("The quick brown fox jumps over the lazy dog")
        >>> sh2 = Simhash("The quick brown fox jumps over a lazy dog")
        >>> sh1.distance(sh2)
        3
        >>> sh1.similarity(sh2)
        95.3125
    """

    def __init__(self, text: str, hash_bits: int = 64) -> None:
        """Initialize Simhash with text content.

        Args:
            text: Text content to hash
            hash_bits: Number of bits in fingerprint (default: 64)

        Raises:
            ValueError: If hash_bits is not positive or text is empty
        """
        if hash_bits <= 0:
            raise ValueError(f"hash_bits must be positive, got {hash_bits}")

        if not text or not text.strip():
            raise ValueError("text must be non-empty")

        self.hash_bits = hash_bits
        self.fingerprint = self._generate_fingerprint(text)

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Converts to lowercase, removes punctuation, and splits on whitespace.
        Filters out empty tokens.

        Args:
            text: Text to tokenize

        Returns:
            List of normalized word tokens
        """
        # Convert to lowercase
        text = text.lower()

        # Replace punctuation and special characters with spaces
        text = re.sub(r"[^\w\s]", " ", text)

        # Split on whitespace and filter empty strings
        tokens = [token for token in text.split() if token]

        return tokens

    def _hash_token(self, token: str) -> int:
        """Generate hash for a token.

        Uses MD5 hash and converts to integer. MD5 is fast and provides
        good distribution for Simhash purposes.

        Args:
            token: Token to hash

        Returns:
            Integer hash value
        """
        # Generate MD5 hash
        hash_digest = hashlib.md5(token.encode("utf-8")).hexdigest()

        # Convert hex to integer and truncate to hash_bits
        hash_int = int(hash_digest, 16)

        # Mask to hash_bits length
        mask = (1 << self.hash_bits) - 1
        return hash_int & mask

    def _generate_fingerprint(self, text: str) -> int:
        """Generate Simhash fingerprint from text.

        Algorithm:
        1. Tokenize text
        2. For each token, compute hash
        3. For each bit in hash, increment or decrement vector position
        4. Convert vector to binary fingerprint

        Args:
            text: Text to fingerprint

        Returns:
            64-bit integer fingerprint
        """
        # Initialize vector with zeros
        vector = [0] * self.hash_bits

        # Get tokens
        tokens = self._tokenize(text)

        if not tokens:
            raise ValueError("No tokens extracted from text")

        # Process each token
        for token in tokens:
            token_hash = self._hash_token(token)

            # Update vector based on hash bits
            for i in range(self.hash_bits):
                # Check if bit i is set in token_hash
                if token_hash & (1 << i):
                    vector[i] += 1  # Increment for 1
                else:
                    vector[i] -= 1  # Decrement for 0

        # Convert vector to fingerprint
        fingerprint = 0
        for i in range(self.hash_bits):
            if vector[i] > 0:
                fingerprint |= 1 << i

        return fingerprint

    def distance(self, other: Simhash) -> int:
        """Calculate Hamming distance between two fingerprints.

        Hamming distance is the number of bit positions where the two
        fingerprints differ.

        Args:
            other: Another Simhash instance to compare with

        Returns:
            Hamming distance (0 to hash_bits)

        Raises:
            ValueError: If hash_bits don't match
        """
        if self.hash_bits != other.hash_bits:
            raise ValueError(
                f"Cannot compare fingerprints with different bit lengths: "
                f"{self.hash_bits} vs {other.hash_bits}"
            )

        # XOR gives bits that differ
        xor_result = self.fingerprint ^ other.fingerprint

        # Count set bits (Hamming distance)
        distance = bin(xor_result).count("1")

        return distance

    def similarity(self, other: Simhash) -> float:
        """Calculate similarity percentage between two fingerprints.

        Similarity is calculated as: (1 - distance/hash_bits) * 100

        Args:
            other: Another Simhash instance to compare with

        Returns:
            Similarity percentage (0.0 to 100.0)

        Raises:
            ValueError: If hash_bits don't match
        """
        dist = self.distance(other)
        similarity_pct = (1 - dist / self.hash_bits) * 100
        return similarity_pct

    @property
    def hex(self) -> str:
        """Get fingerprint as hexadecimal string.

        Returns:
            Hex string representation of fingerprint
        """
        # Calculate number of hex digits needed
        hex_digits = (self.hash_bits + 3) // 4
        return f"{self.fingerprint:0{hex_digits}x}"

    @property
    def binary(self) -> str:
        """Get fingerprint as binary string.

        Returns:
            Binary string representation of fingerprint
        """
        return f"{self.fingerprint:0{self.hash_bits}b}"

    def __eq__(self, other: object) -> bool:
        """Check equality with another Simhash.

        Args:
            other: Object to compare with

        Returns:
            True if fingerprints and hash_bits match
        """
        if not isinstance(other, Simhash):
            return NotImplemented
        return self.fingerprint == other.fingerprint and self.hash_bits == other.hash_bits

    def __hash__(self) -> int:
        """Get hash of this Simhash.

        Returns:
            Hash value
        """
        return hash((self.fingerprint, self.hash_bits))

    def __repr__(self) -> str:
        """Get string representation.

        Returns:
            String representation
        """
        return f"Simhash(fingerprint=0x{self.hex}, bits={self.hash_bits})"


def compare_texts(text1: str, text2: str, hash_bits: int = 64) -> tuple[int, float]:
    """Compare two texts using Simhash.

    Convenience function for quick text comparison.

    Args:
        text1: First text
        text2: Second text
        hash_bits: Number of bits in fingerprint (default: 64)

    Returns:
        Tuple of (hamming_distance, similarity_percentage)

    Example:
        >>> distance, similarity = compare_texts(
        ...     "The quick brown fox",
        ...     "The quick brown dog"
        ... )
        >>> print(f"Distance: {distance}, Similarity: {similarity:.2f}%")
    """
    sh1 = Simhash(text1, hash_bits=hash_bits)
    sh2 = Simhash(text2, hash_bits=hash_bits)
    return sh1.distance(sh2), sh1.similarity(sh2)


def find_near_duplicates(
    texts: Iterable[str], threshold: int = 3, hash_bits: int = 64
) -> list[tuple[int, int, int, float]]:
    """Find near-duplicate pairs in a collection of texts.

    Args:
        texts: Iterable of text strings
        threshold: Maximum Hamming distance for near-duplicates (default: 3)
        hash_bits: Number of bits in fingerprint (default: 64)

    Returns:
        List of tuples: (index1, index2, distance, similarity)
        where index1 < index2 and distance <= threshold

    Example:
        >>> texts = [
        ...     "The quick brown fox",
        ...     "The quick brown dog",
        ...     "A completely different text",
        ...     "The quick brown fox jumps"
        ... ]
        >>> duplicates = find_near_duplicates(texts, threshold=5)
        >>> for i, j, dist, sim in duplicates:
        ...     print(f"Texts {i} and {j}: distance={dist}, similarity={sim:.1f}%")
    """
    # Generate fingerprints
    text_list = list(texts)
    fingerprints = [Simhash(text, hash_bits=hash_bits) for text in text_list]

    # Find pairs within threshold
    duplicates = []
    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            distance = fingerprints[i].distance(fingerprints[j])
            if distance <= threshold:
                similarity = fingerprints[i].similarity(fingerprints[j])
                duplicates.append((i, j, distance, similarity))

    return duplicates
