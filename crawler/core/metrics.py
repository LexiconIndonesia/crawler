"""Prometheus metrics configuration."""

from prometheus_client import Counter, Gauge, Histogram

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

# Crawler Metrics
crawl_tasks_total = Counter(
    "crawl_tasks_total",
    "Total crawl tasks received",
    ["task_type"]
)

crawl_tasks_completed_total = Counter(
    "crawl_tasks_completed_total",
    "Total crawl tasks completed",
    ["task_type", "status"]
)

crawl_tasks_failed_total = Counter(
    "crawl_tasks_failed_total",
    "Total crawl tasks failed",
    ["task_type", "error_type"]
)

crawl_duration_seconds = Histogram(
    "crawl_duration_seconds",
    "Crawl duration in seconds",
    ["task_type"]
)

active_crawl_tasks = Gauge(
    "active_crawl_tasks",
    "Number of currently active crawl tasks"
)

# Browser Metrics
browser_sessions_active = Gauge(
    "browser_sessions_active",
    "Number of active browser sessions"
)

browser_page_load_seconds = Histogram(
    "browser_page_load_seconds",
    "Browser page load time in seconds"
)

# Queue Metrics
queue_messages_pending = Gauge(
    "queue_messages_pending",
    "Number of pending messages in queue",
    ["queue_name"]
)

queue_messages_processed_total = Counter(
    "queue_messages_processed_total",
    "Total messages processed from queue",
    ["queue_name"]
)

# Database Metrics
db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections"
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type"]
)

# Cache Metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type"]
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type"]
)
