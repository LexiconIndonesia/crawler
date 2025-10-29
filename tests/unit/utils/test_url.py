"""Unit tests for URL normalization utilities."""

import hashlib

import pytest

from crawler.utils.url import (
    are_urls_equivalent,
    hash_url,
    normalize_and_hash,
    normalize_url,
)


class TestNormalizeURL:
    """Tests for URL normalization utility."""

    def test_normalize_basic_url(self) -> None:
        """Test normalization of a basic URL without parameters."""
        url = "https://example.com/path"
        result = normalize_url(url)
        assert result == "https://example.com/path"

    def test_remove_tracking_parameters(self) -> None:
        """Test removal of common tracking parameters."""
        url = "https://example.com/page?utm_source=facebook&utm_medium=social&page=2"
        result = normalize_url(url)
        # Should remove utm_* but keep semantic parameter 'page'
        assert result == "https://example.com/page?page=2"

    def test_remove_google_analytics_parameters(self) -> None:
        """Test removal of Google Analytics parameters."""
        url = "https://example.com/page?utm_campaign=summer&utm_term=shoes&id=123"
        result = normalize_url(url)
        assert result == "https://example.com/page?id=123"

    def test_remove_facebook_tracking(self) -> None:
        """Test removal of Facebook tracking parameters."""
        url = "https://example.com/article?fbclid=IwAR123&fb_source=share&category=news"
        result = normalize_url(url)
        assert result == "https://example.com/article?category=news"

    def test_remove_google_ads_tracking(self) -> None:
        """Test removal of Google Ads tracking parameters."""
        url = "https://example.com/product?gclid=abc123&gclsrc=aw.ds&product=shoes"
        result = normalize_url(url)
        assert result == "https://example.com/product?product=shoes"

    def test_remove_multiple_tracking_platforms(self) -> None:
        """Test removal of tracking parameters from multiple platforms."""
        url = "https://example.com/page?utm_source=google&fbclid=abc&msclkid=def&page=1"
        result = normalize_url(url)
        assert result == "https://example.com/page?page=1"

    def test_sort_query_parameters(self) -> None:
        """Test alphabetical sorting of query parameters."""
        url = "https://example.com/page?z=3&a=1&m=2&b=4"
        result = normalize_url(url)
        assert result == "https://example.com/page?a=1&b=4&m=2&z=3"

    def test_sort_with_tracking_removal(self) -> None:
        """Test parameter sorting after removing tracking parameters."""
        url = "https://example.com/page?utm_source=fb&z=3&a=1&utm_medium=cpc"
        result = normalize_url(url)
        assert result == "https://example.com/page?a=1&z=3"

    def test_lowercase_scheme(self) -> None:
        """Test conversion of scheme to lowercase."""
        url = "HTTPS://example.com/path"
        result = normalize_url(url)
        assert result.startswith("https://")

    def test_lowercase_hostname(self) -> None:
        """Test conversion of hostname to lowercase."""
        url = "https://EXAMPLE.COM/path"
        result = normalize_url(url)
        assert result == "https://example.com/path"

    def test_preserve_path_case(self) -> None:
        """Test that URL path case is preserved."""
        url = "https://example.com/Path/To/Resource"
        result = normalize_url(url)
        assert result == "https://example.com/Path/To/Resource"

    def test_remove_fragment(self) -> None:
        """Test removal of URL fragments."""
        url = "https://example.com/page#section"
        result = normalize_url(url)
        assert result == "https://example.com/page"

    def test_remove_fragment_with_query(self) -> None:
        """Test removal of fragments with query parameters."""
        url = "https://example.com/page?id=123#section"
        result = normalize_url(url)
        assert result == "https://example.com/page?id=123"

    def test_preserve_fragment_when_disabled(self) -> None:
        """Test preserving fragments when remove_fragment=False."""
        url = "https://example.com/page?id=123#section"
        result = normalize_url(url, remove_fragment=False)
        assert result == "https://example.com/page?id=123#section"

    def test_preserve_semantic_parameters(self) -> None:
        """Test preservation of semantic parameters."""
        semantic_params = [
            "page",
            "category",
            "id",
            "search",
            "q",
            "sort",
            "filter",
            "limit",
            "offset",
        ]
        for param in semantic_params:
            url = f"https://example.com/page?utm_source=fb&{param}=test"
            result = normalize_url(url)
            assert f"{param}=test" in result
            assert "utm_source" not in result

    def test_preserve_custom_parameters(self) -> None:
        """Test preservation of custom parameters."""
        url = "https://example.com/page?utm_source=fb&custom=value&page=1"
        result = normalize_url(url, preserve_params={"custom"})
        assert result == "https://example.com/page?custom=value&page=1"

    def test_disable_tracking_removal(self) -> None:
        """Test disabling tracking parameter removal."""
        url = "https://example.com/page?utm_source=fb&page=1"
        result = normalize_url(url, remove_tracking=False)
        assert "utm_source=fb" in result
        assert "page=1" in result

    def test_disable_param_sorting(self) -> None:
        """Test disabling parameter sorting."""
        url = "https://example.com/page?z=3&a=1&b=2"
        result = normalize_url(url, sort_params=False)
        # Order should be preserved (parse_qs maintains order in Python 3.7+)
        assert result == "https://example.com/page?z=3&a=1&b=2"

    def test_disable_lowercase_scheme_host(self) -> None:
        """Test disabling lowercase conversion for hostname.

        Note: Scheme is always normalized to lowercase per RFC 3986,
        regardless of the lowercase_scheme_host parameter.
        """
        url = "HTTPS://EXAMPLE.COM/path"
        result = normalize_url(url, lowercase_scheme_host=False)
        # Scheme is always lowercase (RFC 3986), but hostname preserves case
        assert result == "https://EXAMPLE.COM/path"

    def test_url_with_port(self) -> None:
        """Test normalization of URL with port number."""
        url = "https://example.com:8080/path?utm_source=fb&page=1"
        result = normalize_url(url)
        assert result == "https://example.com:8080/path?page=1"

    def test_url_with_username_password(self) -> None:
        """Test normalization of URL with credentials."""
        url = "https://user:pass@example.com/path?utm_source=fb"
        result = normalize_url(url)
        assert result == "https://user:pass@example.com/path"

    def test_multiple_values_same_parameter(self) -> None:
        """Test handling of multiple values for the same parameter."""
        # Takes first value when duplicate parameters exist
        url = "https://example.com/page?id=1&id=2&id=3"
        result = normalize_url(url)
        assert result == "https://example.com/page?id=1"

    def test_empty_parameter_values(self) -> None:
        """Test handling of empty parameter values."""
        url = "https://example.com/page?id=&category=tech"
        result = normalize_url(url)
        assert result == "https://example.com/page?category=tech&id="

    def test_url_with_no_parameters(self) -> None:
        """Test URL with no query parameters."""
        url = "https://example.com/path/to/resource"
        result = normalize_url(url)
        assert result == "https://example.com/path/to/resource"

    def test_url_with_trailing_slash(self) -> None:
        """Test URL with trailing slash is preserved."""
        url = "https://example.com/path/"
        result = normalize_url(url)
        assert result == "https://example.com/path/"

    def test_url_with_subdomain(self) -> None:
        """Test URL with subdomain."""
        url = "https://blog.EXAMPLE.com/post?utm_source=fb&id=123"
        result = normalize_url(url)
        assert result == "https://blog.example.com/post?id=123"

    def test_complex_real_world_url(self) -> None:
        """Test normalization of complex real-world URL."""
        url = (
            "HTTPS://WWW.EXAMPLE.COM/products/shoes?"
            "utm_source=google&utm_medium=cpc&utm_campaign=summer2024&"
            "category=running&color=blue&size=10&page=2&sort=price&"
            "fbclid=IwAR123&gclid=abc123#reviews"
        )
        result = normalize_url(url)
        expected = (
            "https://www.example.com/products/shoes?"
            "category=running&color=blue&page=2&size=10&sort=price"
        )
        assert result == expected

    def test_international_domain(self) -> None:
        """Test URL with international domain."""
        url = "https://例え.jp/path?utm_source=fb&page=1"
        result = normalize_url(url)
        assert result == "https://例え.jp/path?page=1"


class TestNormalizeURLEdgeCases:
    """Tests for edge cases in URL normalization."""

    def test_invalid_empty_url(self) -> None:
        """Test that empty URL raises ValueError."""
        with pytest.raises(ValueError, match="URL must be a non-empty string"):
            normalize_url("")

    def test_invalid_none_url(self) -> None:
        """Test that None URL raises ValueError."""
        with pytest.raises(ValueError, match="URL must be a non-empty string"):
            normalize_url(None)  # type: ignore

    def test_invalid_url_no_scheme(self) -> None:
        """Test that URL without scheme raises ValueError."""
        with pytest.raises(ValueError, match="URL must have a scheme and hostname"):
            normalize_url("example.com/path")

    def test_invalid_url_no_hostname(self) -> None:
        """Test that URL without hostname raises ValueError."""
        with pytest.raises(ValueError, match="URL must have a scheme and hostname"):
            normalize_url("https:///path")

    def test_url_with_only_scheme_and_host(self) -> None:
        """Test URL with only scheme and hostname."""
        url = "https://example.com"
        result = normalize_url(url)
        assert result == "https://example.com"

    def test_url_with_whitespace(self) -> None:
        """Test URL with leading/trailing whitespace."""
        url = "  https://example.com/path?page=1  "
        result = normalize_url(url)
        assert result == "https://example.com/path?page=1"

    def test_url_with_encoded_characters(self) -> None:
        """Test URL with percent-encoded characters."""
        url = "https://example.com/path?search=hello%20world&utm_source=fb"
        result = normalize_url(url)
        assert result == "https://example.com/path?search=hello+world"

    def test_url_with_special_characters_in_path(self) -> None:
        """Test URL with special characters in path."""
        url = "https://example.com/path/with/special-chars_123?page=1"
        result = normalize_url(url)
        assert result == "https://example.com/path/with/special-chars_123?page=1"

    def test_http_vs_https(self) -> None:
        """Test that HTTP and HTTPS are treated as different URLs."""
        url1 = "http://example.com/path"
        url2 = "https://example.com/path"
        result1 = normalize_url(url1)
        result2 = normalize_url(url2)
        assert result1 != result2
        assert result1 == "http://example.com/path"
        assert result2 == "https://example.com/path"


class TestAreURLsEquivalent:
    """Tests for URL equivalence checking."""

    def test_equivalent_urls_basic(self) -> None:
        """Test that basic equivalent URLs are detected."""
        url1 = "https://example.com/path"
        url2 = "https://example.com/path"
        assert are_urls_equivalent(url1, url2) is True

    def test_equivalent_urls_different_tracking(self) -> None:
        """Test that URLs with different tracking params are equivalent."""
        url1 = "https://example.com/page?utm_source=facebook&page=2"
        url2 = "https://example.com/page?utm_source=google&page=2"
        assert are_urls_equivalent(url1, url2) is True

    def test_equivalent_urls_different_case(self) -> None:
        """Test that URLs with different case in host are equivalent."""
        url1 = "https://EXAMPLE.com/path"
        url2 = "https://example.com/path"
        assert are_urls_equivalent(url1, url2) is True

    def test_equivalent_urls_different_param_order(self) -> None:
        """Test that URLs with different parameter order are equivalent."""
        url1 = "https://example.com/page?a=1&b=2&c=3"
        url2 = "https://example.com/page?c=3&a=1&b=2"
        assert are_urls_equivalent(url1, url2) is True

    def test_equivalent_urls_with_and_without_fragment(self) -> None:
        """Test that URLs with/without fragments are equivalent."""
        url1 = "https://example.com/page?id=123#section"
        url2 = "https://example.com/page?id=123"
        assert are_urls_equivalent(url1, url2) is True

    def test_non_equivalent_different_paths(self) -> None:
        """Test that URLs with different paths are not equivalent."""
        url1 = "https://example.com/path1"
        url2 = "https://example.com/path2"
        assert are_urls_equivalent(url1, url2) is False

    def test_non_equivalent_different_params(self) -> None:
        """Test that URLs with different semantic params are not equivalent."""
        url1 = "https://example.com/page?page=1"
        url2 = "https://example.com/page?page=2"
        assert are_urls_equivalent(url1, url2) is False

    def test_non_equivalent_different_hosts(self) -> None:
        """Test that URLs with different hosts are not equivalent."""
        url1 = "https://example1.com/path"
        url2 = "https://example2.com/path"
        assert are_urls_equivalent(url1, url2) is False

    def test_invalid_urls_not_equivalent(self) -> None:
        """Test that invalid URLs are not considered equivalent."""
        url1 = "invalid"
        url2 = "also-invalid"
        assert are_urls_equivalent(url1, url2) is False

    def test_one_valid_one_invalid(self) -> None:
        """Test that one valid and one invalid URL are not equivalent."""
        url1 = "https://example.com/path"
        url2 = "invalid"
        assert are_urls_equivalent(url1, url2) is False

    def test_equivalent_with_custom_options(self) -> None:
        """Test equivalence with custom normalization options."""
        url1 = "https://example.com/page?utm_source=fb&custom=1"
        url2 = "https://example.com/page?custom=1"
        # With tracking removal (default)
        assert are_urls_equivalent(url1, url2) is True
        # Without tracking removal
        assert are_urls_equivalent(url1, url2, remove_tracking=False) is False

    def test_complex_equivalent_urls(self) -> None:
        """Test equivalence of complex real-world URLs."""
        url1 = (
            "HTTPS://WWW.Example.COM/products?"
            "utm_source=google&category=shoes&page=1&utm_medium=cpc#section"
        )
        url2 = "https://www.example.com/products?page=1&category=shoes&fbclid=IwAR123"
        assert are_urls_equivalent(url1, url2) is True


class TestHashURL:
    """Tests for URL hashing utility."""

    def test_hash_url_basic(self) -> None:
        """Test basic URL hashing."""
        url = "https://example.com/path"
        result = hash_url(url)
        # Should be a 64-character hex string (SHA-256)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_url_normalized_by_default(self) -> None:
        """Test that URLs are normalized before hashing by default."""
        url1 = "https://example.com/page?utm_source=fb&page=2"
        url2 = "https://example.com/page?page=2"
        # Both should produce the same hash because tracking params are removed
        assert hash_url(url1) == hash_url(url2)

    def test_hash_url_different_tracking_same_hash(self) -> None:
        """Test that different tracking params produce the same hash."""
        url1 = "https://example.com/page?utm_source=facebook&category=tech"
        url2 = "https://example.com/page?utm_source=google&category=tech"
        assert hash_url(url1) == hash_url(url2)

    def test_hash_url_case_insensitive_host(self) -> None:
        """Test that hostname case doesn't affect hash."""
        url1 = "https://EXAMPLE.com/path"
        url2 = "https://example.com/path"
        assert hash_url(url1) == hash_url(url2)

    def test_hash_url_param_order_independent(self) -> None:
        """Test that parameter order doesn't affect hash."""
        url1 = "https://example.com/page?a=1&b=2&c=3"
        url2 = "https://example.com/page?c=3&a=1&b=2"
        assert hash_url(url1) == hash_url(url2)

    def test_hash_url_without_normalization(self) -> None:
        """Test hashing without normalization."""
        url1 = "https://example.com/page?utm_source=fb&page=2"
        url2 = "https://example.com/page?page=2"
        # Should produce different hashes when normalization is disabled
        assert hash_url(url1, normalize=False) != hash_url(url2, normalize=False)

    def test_hash_url_raw_matches_expected(self) -> None:
        """Test that raw hashing produces expected SHA-256."""
        url = "https://example.com/path"
        expected = hashlib.sha256(url.encode("utf-8")).hexdigest()
        result = hash_url(url, normalize=False)
        assert result == expected

    def test_hash_url_different_urls_different_hashes(self) -> None:
        """Test that different URLs produce different hashes."""
        url1 = "https://example.com/path1"
        url2 = "https://example.com/path2"
        assert hash_url(url1) != hash_url(url2)

    def test_hash_url_semantic_params_affect_hash(self) -> None:
        """Test that semantic parameters affect the hash."""
        url1 = "https://example.com/page?page=1"
        url2 = "https://example.com/page?page=2"
        assert hash_url(url1) != hash_url(url2)

    def test_hash_url_invalid_raises_error(self) -> None:
        """Test that invalid URLs raise ValueError when normalized."""
        with pytest.raises(ValueError):
            hash_url("invalid-url", normalize=True)

    def test_hash_url_custom_normalize_options(self) -> None:
        """Test hashing with custom normalization options."""
        url = "https://example.com/page#section"
        # With fragment removal (default)
        hash1 = hash_url(url, normalize=True, remove_fragment=True)
        # Without fragment removal
        hash2 = hash_url(url, normalize=True, remove_fragment=False)
        assert hash1 != hash2


class TestNormalizeAndHash:
    """Tests for normalize_and_hash utility."""

    def test_normalize_and_hash_returns_tuple(self) -> None:
        """Test that normalize_and_hash returns a tuple."""
        url = "https://example.com/path?utm_source=fb&page=1"
        result = normalize_and_hash(url)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_normalize_and_hash_normalized_url(self) -> None:
        """Test that the first element is the normalized URL."""
        url = "HTTPS://EXAMPLE.COM/page?utm_source=fb&page=1"
        normalized, _ = normalize_and_hash(url)
        assert normalized == "https://example.com/page?page=1"

    def test_normalize_and_hash_hash_value(self) -> None:
        """Test that the second element is a valid hash."""
        url = "https://example.com/path"
        _, hash_value = normalize_and_hash(url)
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_normalize_and_hash_consistency(self) -> None:
        """Test that hash matches hash_url result."""
        url = "https://example.com/path?utm_source=fb&page=1"
        normalized, hash_value = normalize_and_hash(url)
        expected_hash = hash_url(url, normalize=True)
        assert hash_value == expected_hash

    def test_normalize_and_hash_same_for_equivalent_urls(self) -> None:
        """Test that equivalent URLs produce the same hash."""
        url1 = "https://example.com/page?utm_source=facebook&page=1"
        url2 = "HTTPS://EXAMPLE.com/page?utm_source=google&page=1"
        _, hash1 = normalize_and_hash(url1)
        _, hash2 = normalize_and_hash(url2)
        assert hash1 == hash2

    def test_normalize_and_hash_with_custom_options(self) -> None:
        """Test normalize_and_hash with custom options."""
        url = "https://example.com/page?utm_source=fb&custom=value"
        normalized, _ = normalize_and_hash(url, preserve_params={"custom"})
        assert "custom=value" in normalized

    def test_normalize_and_hash_invalid_url(self) -> None:
        """Test that invalid URLs raise ValueError."""
        with pytest.raises(ValueError):
            normalize_and_hash("invalid-url")
