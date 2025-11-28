"""Step executors for different execution methods (HTTP, Browser, API, Crawl, Scrape).

This package provides executors for different step execution methods:
- HTTPExecutor: Standard HTTP requests
- BrowserExecutor: Browser automation (Playwright/undetected-chrome)
- APIExecutor: JSON API requests with structured responses
- CrawlExecutor: URL retrieval with pagination support
- ScrapeExecutor: Content extraction from detail pages with batch processing
"""

from crawler.services.step_executors.api_executor import APIExecutor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult
from crawler.services.step_executors.browser_executor import BrowserExecutor
from crawler.services.step_executors.crawl_executor import CrawlExecutor
from crawler.services.step_executors.http_executor import HTTPExecutor
from crawler.services.step_executors.scrape_executor import ScrapeExecutor

__all__ = [
    "APIExecutor",
    "BaseStepExecutor",
    "BrowserExecutor",
    "CrawlExecutor",
    "ExecutionResult",
    "HTTPExecutor",
    "ScrapeExecutor",
]
