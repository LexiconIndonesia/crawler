"""URL normalization utilities for deduplication and comparison."""

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Common tracking parameters used by analytics and marketing platforms
TRACKING_PARAMETERS = {
    # Google Analytics
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_source_platform",
    "utm_creative_format",
    "utm_marketing_tactic",
    # Facebook
    "fbclid",
    "fb_action_ids",
    "fb_action_types",
    "fb_source",
    "fb_ref",
    # Google Ads
    "gclid",
    "gclsrc",
    "dclid",
    # Microsoft/Bing
    "msclkid",
    # Twitter
    "twclid",
    # TikTok
    "ttclid",
    # LinkedIn
    "li_fat_id",
    # Mailchimp
    "mc_cid",
    "mc_eid",
    # HubSpot
    "_hsenc",
    "_hsmi",
    # Other common tracking
    "ref",
    "referrer",
    "source",
    "campaign",
    "medium",
}

# Semantic parameters that should be preserved (case-sensitive names)
SEMANTIC_PARAMETERS = {
    "page",
    "p",
    "category",
    "cat",
    "id",
    "item",
    "product",
    "search",
    "q",
    "query",
    "sort",
    "order",
    "filter",
    "limit",
    "offset",
    "lang",
    "locale",
    "size",
    "color",
    "variant",
    "tab",
    "section",
}


def normalize_url(
    url: str,
    *,
    remove_fragment: bool = True,
    remove_tracking: bool = True,
    sort_params: bool = True,
    lowercase_scheme_host: bool = True,
    preserve_params: set[str] | None = None,
) -> str:
    """Normalize a URL for deduplication and comparison.

    This function standardizes URLs by:
    - Removing tracking parameters (utm_*, fbclid, etc.)
    - Sorting query parameters alphabetically
    - Converting hostname to lowercase (scheme is always lowercase per RFC 3986)
    - Removing fragments (e.g., #section)
    - Preserving semantic parameters (page, category, id, etc.)

    Args:
        url: The URL to normalize
        remove_fragment: Whether to remove URL fragments (default: True)
        remove_tracking: Whether to remove tracking parameters (default: True)
        sort_params: Whether to sort query parameters (default: True)
        lowercase_scheme_host: Whether to lowercase hostname (default: True).
            Note: Scheme is always normalized to lowercase per RFC 3986.
        preserve_params: Additional parameter names to preserve beyond semantic ones

    Returns:
        Normalized URL string

    Raises:
        ValueError: If the URL is invalid or cannot be parsed

    Example:
        >>> normalize_url("https://Example.com/page?utm_source=fb&page=2&category=tech")
        'https://example.com/page?category=tech&page=2'

        >>> normalize_url("HTTP://EXAMPLE.COM/Path?z=3&a=1&b=2")
        'http://example.com/Path?a=1&b=2&z=3'

        >>> normalize_url("https://example.com/page#section")
        'https://example.com/page'
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e

    # Validate that we have at least a scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL must have a scheme and hostname: {url}")

    # Process scheme and hostname
    scheme = parsed.scheme.lower() if lowercase_scheme_host else parsed.scheme
    netloc = parsed.netloc.lower() if lowercase_scheme_host else parsed.netloc

    # Keep path as-is (preserve case for paths)
    path = parsed.path

    # Process query parameters
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)

        # Determine which parameters to keep
        preserved_params = SEMANTIC_PARAMETERS.copy()
        if preserve_params:
            preserved_params.update(preserve_params)

        # Filter out tracking parameters if enabled
        if remove_tracking:
            # Keep only semantic parameters and custom preserved ones
            params = {
                k: v
                for k, v in params.items()
                if k in preserved_params or k not in TRACKING_PARAMETERS
            }

        # Convert lists to single values (take first value)
        # This handles ?param=value1&param=value2 -> param=value1
        params_dict = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}

        # Sort parameters if enabled
        if sort_params:
            query = urlencode(sorted(params_dict.items()), doseq=False)
        else:
            query = urlencode(params_dict, doseq=False)
    else:
        query = ""

    # Remove fragment if enabled
    fragment = "" if remove_fragment else parsed.fragment

    # Reconstruct the URL
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, fragment))

    return normalized


def are_urls_equivalent(url1: str, url2: str, **normalize_kwargs: Any) -> bool:
    """Check if two URLs are equivalent after normalization.

    Args:
        url1: First URL to compare
        url2: Second URL to compare
        **normalize_kwargs: Additional arguments passed to normalize_url()

    Returns:
        True if URLs are equivalent after normalization, False otherwise

    Example:
        >>> are_urls_equivalent(
        ...     "https://example.com/page?utm_source=fb&page=2",
        ...     "https://EXAMPLE.com/page?page=2"
        ... )
        True
    """
    try:
        norm1 = normalize_url(url1, **normalize_kwargs)
        norm2 = normalize_url(url2, **normalize_kwargs)
        return norm1 == norm2
    except ValueError:
        return False
