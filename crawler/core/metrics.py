"""Prometheus metrics configuration."""

from prometheus_client import Counter, Gauge, Histogram

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["method", "endpoint"]
)

# Crawler Metrics
crawl_tasks_total = Counter("crawl_tasks_total", "Total crawl tasks received", ["task_type"])

crawl_tasks_completed_total = Counter(
    "crawl_tasks_completed_total", "Total crawl tasks completed", ["task_type", "status"]
)

crawl_tasks_failed_total = Counter(
    "crawl_tasks_failed_total", "Total crawl tasks failed", ["task_type", "error_type"]
)

crawl_duration_seconds = Histogram(
    "crawl_duration_seconds", "Crawl duration in seconds", ["task_type"]
)

active_crawl_tasks = Gauge("active_crawl_tasks", "Number of currently active crawl tasks")

# Browser Metrics
browser_sessions_active = Gauge("browser_sessions_active", "Number of active browser sessions")

browser_page_load_seconds = Histogram(
    "browser_page_load_seconds", "Browser page load time in seconds"
)

browser_pool_size = Gauge("browser_pool_size", "Total number of browser instances in pool")

browser_pool_healthy = Gauge("browser_pool_healthy", "Number of healthy browser instances")

browser_pool_contexts_available = Gauge(
    "browser_pool_contexts_available", "Number of available browser contexts in pool"
)

browser_pool_queue_size = Gauge(
    "browser_pool_queue_size", "Number of requests waiting for browser contexts"
)

browser_pool_queue_wait_seconds = Histogram(
    "browser_pool_queue_wait_seconds", "Time spent waiting in queue for browser context"
)

browser_crashes_total = Counter(
    "browser_crashes_total", "Total number of browser crashes detected", ["browser_type"]
)

browser_crash_recoveries_total = Counter(
    "browser_crash_recoveries_total", "Total number of successful browser crash recoveries"
)

# Queue Metrics
queue_messages_pending = Gauge(
    "queue_messages_pending", "Number of pending messages in queue", ["queue_name"]
)

queue_messages_processed_total = Counter(
    "queue_messages_processed_total", "Total messages processed from queue", ["queue_name"]
)

# Database Metrics
db_connections_active = Gauge("db_connections_active", "Number of active database connections")

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds", "Database query duration in seconds", ["query_type"]
)

# Cache Metrics
cache_hits_total = Counter("cache_hits_total", "Total cache hits", ["cache_type"])

cache_misses_total = Counter("cache_misses_total", "Total cache misses", ["cache_type"])

# Memory Metrics
system_memory_usage_percent = Gauge("system_memory_usage_percent", "System memory usage percentage")

system_memory_used_bytes = Gauge("system_memory_used_bytes", "System memory used in bytes")

system_memory_available_bytes = Gauge(
    "system_memory_available_bytes", "System memory available in bytes"
)

browser_memory_usage_bytes = Gauge(
    "browser_memory_usage_bytes", "Browser process memory usage in bytes", ["browser_index"]
)

memory_alerts_total = Counter(
    "memory_alerts_total", "Total memory alerts triggered", ["level", "type"]
)

# Dead Letter Queue Metrics
dlq_entries_total = Counter(
    "dlq_entries_total", "Total jobs added to Dead Letter Queue", ["error_category", "job_type"]
)

dlq_entries_unresolved = Gauge("dlq_entries_unresolved", "Number of unresolved entries in DLQ")

dlq_entries_by_category = Gauge(
    "dlq_entries_by_category", "Number of DLQ entries by error category", ["error_category"]
)

dlq_retry_attempts_total = Counter(
    "dlq_retry_attempts_total", "Total manual retry attempts from DLQ", ["success"]
)

dlq_resolutions_total = Counter("dlq_resolutions_total", "Total DLQ entries manually resolved")

dlq_oldest_unresolved_age_seconds = Gauge(
    "dlq_oldest_unresolved_age_seconds", "Age of oldest unresolved DLQ entry in seconds"
)

# Scheduled Job Processor Metrics
scheduled_jobs_processed_total = Counter(
    "scheduled_jobs_processed_total",
    "Total scheduled jobs successfully processed and enqueued",
    ["processing_type"],  # normal, catchup
)

scheduled_jobs_skipped_total = Counter(
    "scheduled_jobs_skipped_total",
    "Total scheduled jobs skipped (outside catch-up threshold)",
    ["reason"],  # missed_threshold, etc.
)
