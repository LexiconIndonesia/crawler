"""Example usage of the pagination system.

This file demonstrates how to use the intelligent pagination detection
and URL generation features in the Lexicon Crawler.

Run this example:
    uv run python examples/pagination_usage.py
"""

import asyncio

from crawler.api.generated import PaginationConfig
from crawler.services.pagination import PaginationService


def example_1_auto_detection():
    """Example 1: Automatic pagination pattern detection."""
    print("\n=== Example 1: Auto-Detection ===\n")

    service = PaginationService()

    # The service will automatically detect the pagination pattern
    # from the seed URL without any configuration!

    # Example with query parameter pagination
    seed_url = "https://example.com/products?page=5&category=tech"
    config = PaginationConfig(enabled=True, max_pages=10)

    urls = service.generate_pagination_urls(seed_url, config)

    print(f"Seed URL: {seed_url}")
    print(f"Pattern detected: {service.get_pagination_strategy(seed_url, config)}")
    print(f"Generated {len(urls)} URLs:")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")


def example_2_arbitrary_start_page():
    """Example 2: Starting from arbitrary page number."""
    print("\n=== Example 2: Starting from Page 10 ===\n")

    service = PaginationService()

    # You can start from any page, not just page 1!
    seed_url = "https://news.example.com/articles?page=10"
    config = PaginationConfig(enabled=True, max_pages=15)

    urls = service.generate_pagination_urls(seed_url, config)

    print(f"Seed URL: {seed_url}")
    print(f"Generated URLs from page 10 to 15 ({len(urls)} URLs):")
    for url in urls:
        # Extract page number for display
        page = url.split("page=")[1] if "page=" in url else "?"
        print(f"  - Page {page}")


def example_3_path_segment_pagination():
    """Example 3: Path segment pagination pattern."""
    print("\n=== Example 3: Path Segment Pagination ===\n")

    service = PaginationService()

    # Works with /page/N pattern too
    seed_url = "https://blog.example.com/category/technology/page/3"
    config = PaginationConfig(enabled=True, max_pages=7)

    urls = service.generate_pagination_urls(seed_url, config)

    print(f"Seed URL: {seed_url}")
    print(f"Pattern type: {service.get_pagination_strategy(seed_url, config)}")
    print(f"Generated {len(urls)} URLs:")
    for url in urls:
        print(f"  - {url}")


def example_4_url_template():
    """Example 4: Using explicit URL template."""
    print("\n=== Example 4: Explicit URL Template ===\n")

    service = PaginationService()

    # You can provide an explicit template for complete control
    config = PaginationConfig(
        enabled=True,
        url_template="https://api.example.com/data?page={page}&sort=date",
        start_page=1,
        max_pages=5,
    )

    # Seed URL doesn't matter when using template
    urls = service.generate_pagination_urls(
        seed_url="https://api.example.com/data?page=1", config=config
    )

    print("Template: https://api.example.com/data?page={page}&sort=date")
    print(f"Generated {len(urls)} URLs:")
    for url in urls:
        print(f"  - {url}")


def example_5_offset_based():
    """Example 5: Offset-based pagination."""
    print("\n=== Example 5: Offset-Based Pagination ===\n")

    service = PaginationService()

    # Automatically handles offset-based pagination (e.g., REST APIs)
    seed_url = "https://api.example.com/items?offset=40&limit=20"
    config = PaginationConfig(enabled=True, max_pages=5)

    urls = service.generate_pagination_urls(seed_url, config)

    print(f"Seed URL: {seed_url}")
    print("The service detects this is offset-based and calculates correctly:")
    print(f"  - Page 3 (offset=40) is the seed")
    print(f"Generated {len(urls)} URLs:")
    for i, url in enumerate(urls, 3):  # Start from page 3
        offset = url.split("offset=")[1].split("&")[0] if "offset=" in url else "?"
        print(f"  - Page {i}: offset={offset}")


async def example_6_with_stop_detection():
    """Example 6: Sequential crawling with stop detection."""
    print("\n=== Example 6: Live Stop Detection ===\n")

    service = PaginationService()

    # Simulated fetch function (replace with real HTTP client)
    async def mock_fetch(url: str) -> tuple[int, bytes]:
        """Simulate fetching a page."""
        page_num = url.split("page=")[1] if "page=" in url else "1"
        if int(page_num) > 3:
            # Simulate 404 at page 4
            return 404, b"Not Found"
        content = f"Content for page {page_num}. " * 20
        return 200, content.encode()

    config = PaginationConfig(enabled=True, max_pages=10)

    print("Crawling with live stop detection...")
    print("(Will automatically stop when 404 is encountered)\n")

    pages_crawled = 0
    async for url, status_code, content in service.generate_with_stop_detection(
        seed_url="https://example.com/page?page=1",
        config=config,
        fetch_fn=mock_fetch,
    ):
        pages_crawled += 1
        print(
            f"  ✓ Crawled: {url} (status: {status_code}, size: {len(content)} bytes)"
        )

    print(f"\nStopped after {pages_crawled} pages (detected 404)")


def example_7_strategy_detection():
    """Example 7: Detecting pagination strategy."""
    print("\n=== Example 7: Strategy Detection ===\n")

    service = PaginationService()

    test_cases = [
        ("https://example.com/products?page=5", "auto_detected"),
        ("https://example.com/products", "disabled"),
        ("https://example.com/page/3", "auto_detected"),
    ]

    for url, _ in test_cases:
        config = PaginationConfig(enabled=True, max_pages=10)
        strategy = service.get_pagination_strategy(url, config)
        should_use_selector = service.should_use_selector_based_pagination(url, config)

        print(f"URL: {url}")
        print(f"  Strategy: {strategy}")
        print(f"  Needs selector: {should_use_selector}")
        print()


def example_8_practical_use_case():
    """Example 8: Real-world use case - E-commerce scraping."""
    print("\n=== Example 8: E-commerce Scraping ===\n")

    service = PaginationService()

    # Imagine scraping an e-commerce site that has paginated product listings
    seed_url = "https://shop.example.com/search?q=laptop&price_max=1000&page=1"

    config = PaginationConfig(
        enabled=True,
        max_pages=20,  # Don't crawl more than 20 pages
    )

    urls = service.generate_pagination_urls(seed_url, config)

    print("Task: Scrape all laptops under $1000")
    print(f"Starting from: {seed_url}")
    print(f"Total pages to crawl: {len(urls)}")
    print("\nPagination URLs generated (first 5):")
    for url in urls[:5]:
        print(f"  - {url}")
    if len(urls) > 5:
        print(f"  ... and {len(urls) - 5} more")

    print("\n✓ URLs generated instantly without DOM parsing!")
    print("✓ Preserves all query parameters (q, price_max)")
    print("✓ Ready for parallel crawling")


def main():
    """Run all examples."""
    print("=" * 60)
    print("    Lexicon Crawler - Pagination System Examples")
    print("=" * 60)

    # Synchronous examples
    example_1_auto_detection()
    example_2_arbitrary_start_page()
    example_3_path_segment_pagination()
    example_4_url_template()
    example_5_offset_based()
    example_7_strategy_detection()
    example_8_practical_use_case()

    # Async example
    print("\n" + "=" * 60)
    asyncio.run(example_6_with_stop_detection())

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
