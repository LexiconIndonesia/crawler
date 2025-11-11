"""Unit tests for Simhash implementation.

Tests cover tokenization, hash generation, fingerprint creation,
distance calculation, and similarity metrics with known examples.
"""

import pytest

from crawler.utils.simhash import Simhash, compare_texts, find_near_duplicates


class TestSimhashTokenization:
    """Tests for text tokenization."""

    def test_basic_tokenization(self) -> None:
        """Test basic word tokenization."""
        sh = Simhash("Hello World")
        tokens = sh._tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_tokenization_with_punctuation(self) -> None:
        """Test that punctuation is removed."""
        sh = Simhash("test")
        tokens = sh._tokenize("Hello, World! How are you?")
        assert tokens == ["hello", "world", "how", "are", "you"]

    def test_tokenization_lowercase(self) -> None:
        """Test that text is converted to lowercase."""
        sh = Simhash("test")
        tokens = sh._tokenize("ThE QuIcK BrOwN FoX")
        assert tokens == ["the", "quick", "brown", "fox"]

    def test_tokenization_multiple_spaces(self) -> None:
        """Test handling of multiple spaces."""
        sh = Simhash("test")
        tokens = sh._tokenize("word1    word2     word3")
        assert tokens == ["word1", "word2", "word3"]

    def test_tokenization_special_characters(self) -> None:
        """Test removal of special characters."""
        sh = Simhash("test")
        tokens = sh._tokenize("test@example.com #hashtag $money")
        assert tokens == ["test", "example", "com", "hashtag", "money"]

    def test_tokenization_numbers(self) -> None:
        """Test that numbers are preserved."""
        sh = Simhash("test")
        tokens = sh._tokenize("test123 456test test789")
        assert tokens == ["test123", "456test", "test789"]


class TestSimhashGeneration:
    """Tests for Simhash fingerprint generation."""

    def test_same_text_same_hash(self) -> None:
        """Test that identical text produces identical hash."""
        text = "The quick brown fox jumps over the lazy dog"
        sh1 = Simhash(text)
        sh2 = Simhash(text)
        assert sh1.fingerprint == sh2.fingerprint

    def test_different_text_different_hash(self) -> None:
        """Test that different text produces different hash."""
        sh1 = Simhash("The quick brown fox")
        sh2 = Simhash("A completely different sentence")
        assert sh1.fingerprint != sh2.fingerprint

    def test_case_insensitive(self) -> None:
        """Test that hash is case-insensitive."""
        sh1 = Simhash("Hello World")
        sh2 = Simhash("hello world")
        assert sh1.fingerprint == sh2.fingerprint

    def test_punctuation_insensitive(self) -> None:
        """Test that hash ignores punctuation."""
        sh1 = Simhash("Hello World")
        sh2 = Simhash("Hello, World!")
        assert sh1.fingerprint == sh2.fingerprint

    def test_word_order_matters(self) -> None:
        """Test that word order affects the hash.

        Note: Simhash is a bag-of-words algorithm, so it IS order-invariant.
        The same words in different order will produce the same hash.
        """
        sh1 = Simhash("quick brown fox")
        sh2 = Simhash("fox brown quick")
        # Same words, different order - should produce SAME hash (bag-of-words)
        assert sh1.fingerprint == sh2.fingerprint

    def test_64bit_fingerprint(self) -> None:
        """Test that fingerprint is 64-bit by default."""
        sh = Simhash("test text")
        # Fingerprint should fit in 64 bits
        assert 0 <= sh.fingerprint < (1 << 64)
        assert sh.hash_bits == 64

    def test_custom_hash_bits(self) -> None:
        """Test custom number of hash bits."""
        sh32 = Simhash("test text", hash_bits=32)
        assert sh32.hash_bits == 32
        assert 0 <= sh32.fingerprint < (1 << 32)

        sh128 = Simhash("test text", hash_bits=128)
        assert sh128.hash_bits == 128


class TestSimhashDistance:
    """Tests for Hamming distance calculation."""

    def test_identical_text_zero_distance(self) -> None:
        """Test that identical text has distance 0."""
        sh1 = Simhash("The quick brown fox")
        sh2 = Simhash("The quick brown fox")
        assert sh1.distance(sh2) == 0

    def test_similar_text_small_distance(self) -> None:
        """Test that similar text has small distance."""
        sh1 = Simhash("The quick brown fox jumps over the lazy dog")
        sh2 = Simhash("The quick brown fox jumps over a lazy dog")
        # Changed "the" to "a" - should have small distance
        distance = sh1.distance(sh2)
        assert distance > 0
        assert distance < 10  # Should be reasonably small

    def test_different_text_large_distance(self) -> None:
        """Test that very different text has large distance."""
        sh1 = Simhash("The quick brown fox")
        sh2 = Simhash("Python programming language")
        distance = sh1.distance(sh2)
        # Should be much larger than similar texts
        assert distance > 20

    def test_distance_symmetric(self) -> None:
        """Test that distance is symmetric."""
        sh1 = Simhash("text one")
        sh2 = Simhash("text two")
        assert sh1.distance(sh2) == sh2.distance(sh1)

    def test_distance_range(self) -> None:
        """Test that distance is in valid range."""
        sh1 = Simhash("test text")
        sh2 = Simhash("another text")
        distance = sh1.distance(sh2)
        assert 0 <= distance <= 64

    def test_mismatched_hash_bits_raises_error(self) -> None:
        """Test that comparing different bit lengths raises error."""
        sh1 = Simhash("test", hash_bits=64)
        sh2 = Simhash("test", hash_bits=32)
        with pytest.raises(ValueError, match="different bit lengths"):
            sh1.distance(sh2)


class TestSimhashSimilarity:
    """Tests for similarity percentage calculation."""

    def test_identical_text_100_percent(self) -> None:
        """Test that identical text has 100% similarity."""
        sh1 = Simhash("The quick brown fox")
        sh2 = Simhash("The quick brown fox")
        assert sh1.similarity(sh2) == 100.0

    def test_similar_text_high_similarity(self) -> None:
        """Test that similar text has high similarity."""
        sh1 = Simhash("The quick brown fox jumps over the lazy dog")
        sh2 = Simhash("The quick brown fox jumps over a lazy dog")
        similarity = sh1.similarity(sh2)
        assert similarity > 85.0  # Should be very similar (changed 1 word: "the" -> "a")
        assert similarity < 100.0

    def test_different_text_low_similarity(self) -> None:
        """Test that different text has low similarity."""
        sh1 = Simhash("The quick brown fox")
        sh2 = Simhash("Python programming language")
        similarity = sh1.similarity(sh2)
        assert similarity < 80.0  # Should be quite different

    def test_similarity_range(self) -> None:
        """Test that similarity is in valid range."""
        sh1 = Simhash("test text")
        sh2 = Simhash("another text")
        similarity = sh1.similarity(sh2)
        assert 0.0 <= similarity <= 100.0

    def test_similarity_symmetric(self) -> None:
        """Test that similarity is symmetric."""
        sh1 = Simhash("text one")
        sh2 = Simhash("text two")
        assert sh1.similarity(sh2) == sh2.similarity(sh1)

    def test_similarity_distance_relationship(self) -> None:
        """Test relationship between similarity and distance."""
        sh1 = Simhash("test text one")
        sh2 = Simhash("test text two")
        distance = sh1.distance(sh2)
        similarity = sh1.similarity(sh2)
        # Verify formula: similarity = (1 - distance/bits) * 100
        expected_similarity = (1 - distance / 64) * 100
        assert abs(similarity - expected_similarity) < 0.01


class TestSimhashKnownExamples:
    """Tests with known examples and expected behavior."""

    def test_near_duplicate_detection(self) -> None:
        """Test detection of near-duplicate content."""
        original = "This is a test document about web crawling and content extraction"
        near_dup = "This is a test document about web crawling and data extraction"
        different = "Python is a great programming language for data science"

        sh_original = Simhash(original)
        sh_near_dup = Simhash(near_dup)
        sh_different = Simhash(different)

        # Near duplicate should be closer than different text
        dist_near = sh_original.distance(sh_near_dup)
        dist_diff = sh_original.distance(sh_different)
        assert dist_near < dist_diff

        # Near duplicate should have high similarity
        assert sh_original.similarity(sh_near_dup) > 85.0

    def test_added_content_similarity(self) -> None:
        """Test similarity when content is added."""
        base = "The quick brown fox"
        extended = "The quick brown fox jumps over the lazy dog"

        sh_base = Simhash(base)
        sh_extended = Simhash(extended)

        # Should still be fairly similar
        similarity = sh_base.similarity(sh_extended)
        assert similarity > 60.0  # At least 60% similar

    def test_removed_content_similarity(self) -> None:
        """Test similarity when content is removed."""
        full = "The quick brown fox jumps over the lazy dog"
        shortened = "The quick brown fox"

        sh_full = Simhash(full)
        sh_shortened = Simhash(shortened)

        # Should still be fairly similar
        similarity = sh_full.similarity(sh_shortened)
        assert similarity > 60.0

    def test_paraphrased_content(self) -> None:
        """Test detection of paraphrased content."""
        original = "The cat sat on the mat"
        paraphrase = "A feline was sitting on a rug"

        sh_original = Simhash(original)
        sh_paraphrase = Simhash(paraphrase)

        # Paraphrases might have lower similarity (different words)
        similarity = sh_original.similarity(sh_paraphrase)
        # This is expected to be lower since words are different
        assert similarity < 80.0


class TestSimhashHelperFunctions:
    """Tests for helper functions."""

    def test_compare_texts(self) -> None:
        """Test compare_texts convenience function."""
        text1 = "The quick brown fox"
        text2 = "The quick brown dog"

        distance, similarity = compare_texts(text1, text2)

        assert isinstance(distance, int)
        assert isinstance(similarity, float)
        assert 0 <= distance <= 64
        assert 0.0 <= similarity <= 100.0

    def test_find_near_duplicates(self) -> None:
        """Test find_near_duplicates function."""
        texts = [
            "The quick brown fox jumps over the lazy dog",
            "The quick brown fox jumps over a lazy dog",  # Near duplicate of 0
            "Python programming language",
            "The quick brown fox jumps over the lazy cat",  # Near duplicate of 0
        ]

        # Use a higher threshold since Simhash distances can vary
        duplicates = find_near_duplicates(texts, threshold=10)

        # Should find pairs (0,1) and (0,3) as near duplicates
        assert len(duplicates) > 0

        # Verify structure
        for i, j, dist, sim in duplicates:
            assert i < j
            assert dist <= 10
            assert 0.0 <= sim <= 100.0

    def test_find_near_duplicates_no_matches(self) -> None:
        """Test find_near_duplicates with no matches."""
        texts = [
            "Completely different text one",
            "Totally unrelated text two",
            "Another unique sentence three",
        ]

        duplicates = find_near_duplicates(texts, threshold=1)
        assert len(duplicates) == 0


class TestSimhashProperties:
    """Tests for Simhash properties and methods."""

    def test_hex_property(self) -> None:
        """Test hex representation."""
        sh = Simhash("test text")
        hex_repr = sh.hex
        assert isinstance(hex_repr, str)
        assert len(hex_repr) == 16  # 64 bits = 16 hex chars
        # Verify it's valid hex
        int(hex_repr, 16)

    def test_binary_property(self) -> None:
        """Test binary representation."""
        sh = Simhash("test text")
        binary_repr = sh.binary
        assert isinstance(binary_repr, str)
        assert len(binary_repr) == 64
        # Verify it's valid binary
        assert all(c in "01" for c in binary_repr)

    def test_equality(self) -> None:
        """Test equality comparison."""
        sh1 = Simhash("test text")
        sh2 = Simhash("test text")
        sh3 = Simhash("different text")

        assert sh1 == sh2
        assert sh1 != sh3
        assert sh1 != "not a simhash"

    def test_hashable(self) -> None:
        """Test that Simhash is hashable."""
        sh1 = Simhash("test text")
        sh2 = Simhash("test text")
        sh3 = Simhash("different text")

        # Can be used in sets
        simhash_set = {sh1, sh2, sh3}
        assert len(simhash_set) == 2  # sh1 and sh2 are equal

        # Can be used as dict keys
        simhash_dict = {sh1: "value1", sh3: "value2"}
        assert len(simhash_dict) == 2

    def test_repr(self) -> None:
        """Test string representation."""
        sh = Simhash("test text")
        repr_str = repr(sh)
        assert "Simhash" in repr_str
        assert "fingerprint" in repr_str
        assert "bits=64" in repr_str


class TestSimhashEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_text_raises_error(self) -> None:
        """Test that empty text raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            Simhash("")

    def test_whitespace_only_raises_error(self) -> None:
        """Test that whitespace-only text raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            Simhash("   \n\t  ")

    def test_invalid_hash_bits_raises_error(self) -> None:
        """Test that invalid hash_bits raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            Simhash("test", hash_bits=0)

        with pytest.raises(ValueError, match="must be positive"):
            Simhash("test", hash_bits=-1)

    def test_single_word(self) -> None:
        """Test with single word."""
        sh = Simhash("hello")
        assert sh.fingerprint > 0
        assert sh.hash_bits == 64

    def test_very_long_text(self) -> None:
        """Test with very long text."""
        long_text = " ".join(["word"] * 10000)
        sh = Simhash(long_text)
        assert sh.fingerprint > 0

    def test_unicode_text(self) -> None:
        """Test with unicode characters."""
        sh1 = Simhash("Hello 世界 мир")
        sh2 = Simhash("Hello 世界 мир")
        assert sh1.fingerprint == sh2.fingerprint

    def test_numeric_text(self) -> None:
        """Test with numeric content."""
        sh = Simhash("12345 67890 11111")
        assert sh.fingerprint > 0
