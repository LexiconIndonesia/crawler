# Browser Pool Manager

The browser pool manager provides efficient browser automation by maintaining a pool of browser instances that can be reused across multiple requests.

## Features

- **Configurable Pool Size**: Control the number of browser instances (default: 3)
- **Context Management**: Multiple contexts per browser (default: 5 per browser)
- **Health Checks**: Periodic health checks to ensure browser instances are functional
- **Graceful Shutdown**: Proper cleanup of all browser resources
- **Prometheus Metrics**: Comprehensive metrics for monitoring pool status
- **Automatic Fallback**: Falls back to per-request browsers if pool is unavailable

## Configuration

Configure the browser pool in your `.env` file or environment variables:

```bash
# Browser Pool Settings
BROWSER_POOL_SIZE=3                        # Number of browser instances
BROWSER_MAX_CONTEXTS_PER_BROWSER=5         # Max contexts per browser
BROWSER_CONTEXT_TIMEOUT=300                # Timeout for acquiring context (seconds)
BROWSER_HEALTH_CHECK_INTERVAL=60           # Health check interval (seconds)
BROWSER_DEFAULT_TYPE=chromium              # Browser type: chromium, firefox, or webkit
```

## Usage

### Automatic Integration

The browser pool is automatically initialized at application startup and integrated with the dependency injection system. The `BrowserExecutor` automatically uses the pool when available.

### Manual Usage

You can also use the browser pool directly in your code:

```python
from crawler.core.dependencies import BrowserPoolDep

async def my_route(browser_pool: BrowserPoolDep):
    """Example route using browser pool."""
    async with browser_pool.acquire_context() as context:
        page = await context.new_page()
        await page.goto("https://example.com")
        content = await page.content()
        await page.close()
```

### Health Check

Get the health status of the browser pool:

```python
health_status = await browser_pool.health_check()
# Returns:
# {
#     "total_browsers": 3,
#     "healthy_browsers": 3,
#     "unhealthy_browsers": 0,
#     "total_contexts": 5,
#     "browsers": [
#         {"index": 0, "healthy": True, "contexts": 2, "browser_type": "chromium"},
#         {"index": 1, "healthy": True, "contexts": 2, "browser_type": "chromium"},
#         {"index": 2, "healthy": True, "contexts": 1, "browser_type": "chromium"}
#     ]
# }
```

### Pool Statistics

Get current pool statistics:

```python
stats = browser_pool.get_pool_stats()
# Returns:
# {
#     "pool_size": 3,
#     "total_browsers": 3,
#     "total_contexts": 5,
#     "max_contexts": 15,  # 3 browsers * 5 contexts
#     "initialized": True,
#     "shutting_down": False
# }
```

## Architecture

### Components

1. **BrowserPool**: Main pool manager class
   - Manages browser instances lifecycle
   - Provides context acquisition/release
   - Handles health checks
   - Tracks metrics

2. **BrowserInstance**: Wrapper for browser with metadata
   - Tracks active contexts
   - Health status
   - Creation time
   - Last health check time

3. **Context Manager**: `acquire_context()` context manager
   - Automatically acquires and releases contexts
   - Updates metrics
   - Handles timeouts
   - Ensures proper cleanup

### Lifecycle

```
Application Startup
    ↓
Initialize BrowserPool
    ↓
Launch N Browser Instances
    ↓
Start Health Check Loop
    ↓
[Ready for Requests]
    ↓
Acquire Context → Use → Release Context
    ↓
[Continuous Health Checks]
    ↓
Application Shutdown
    ↓
Stop Health Checks
    ↓
Close All Contexts & Browsers
    ↓
Cleanup Resources
```

## Context Lifecycle & Cleanup

Each browser context goes through a clean lifecycle:

1. **Acquire**: Get context from pool (creates new context from browser)
2. **Use**: Perform browser automation
3. **Clean**: Clear cookies, storage, close pages
4. **Close**: Destroy context and return browser to pool

### Automatic Cleanup

Before closing, contexts are automatically cleaned to prevent state leakage:

- **Cookies**: All cookies are cleared via `context.clear_cookies()`
- **Storage**: localStorage and sessionStorage are cleared for all pages
- **Pages**: All open pages are closed
- **Reset**: A blank page is created to ensure clean state

### Error Handling

All cleanup operations are wrapped in try/except to ensure:
- Partial failures don't prevent context closure
- Browser pool remains operational even if cleanup fails
- Errors are logged for debugging but don't propagate

### Implementation

```python
async def _cleanup_context(self, context: BrowserContext) -> None:
    """Clean context state before closing."""
    # Clear cookies
    await context.clear_cookies()

    # Clear storage and close pages
    for page in context.pages:
        await page.evaluate("""() => {
            localStorage.clear();
            sessionStorage.clear();
        }""")
        await page.close()

    # Reset to blank page
    if not context.pages:
        await context.new_page()
```

## Context Queueing

When all browser contexts are in use, new requests are automatically queued in FIFO (first-in-first-out) order.

### How Queueing Works

1. **Immediate Return**: If a context is available, it's returned immediately (< 1ms)
2. **Queue When Full**: If pool is at capacity, request enters a FIFO queue
3. **Automatic Assignment**: When a context is released, next queued request gets it
4. **Timeout Support**: Queue wait respects the configured timeout

### Queue Behavior

```python
# Pool has 3 browsers * 5 contexts = 15 total contexts
# If all 15 are in use, new requests queue automatically

async with browser_pool.acquire_context(timeout=30) as context:
    # If context available: immediate return
    # If pool full: wait in queue up to 30 seconds
    # If timeout: raises TimeoutError
    page = await context.new_page()
```

### Queue Logging

The pool logs queue operations for visibility:

```
context_request_queued - Request entered queue
context_acquired_from_queue - Request got context after waiting
context_acquire_timeout - Request timed out in queue
```

## Metrics

The browser pool exposes the following Prometheus metrics:

- `browser_sessions_active`: Number of active browser contexts
- `browser_pool_size`: Total number of browser instances in pool
- `browser_pool_healthy`: Number of healthy browser instances
- `browser_pool_contexts_available`: Number of available contexts
- `browser_pool_queue_size`: Number of requests currently waiting in queue
- `browser_pool_queue_wait_seconds`: Histogram of time spent waiting in queue

Access metrics at `http://localhost:8000/metrics`

## Error Handling

### Timeout Error

When all contexts are in use, `acquire_context()` will wait up to `browser_context_timeout` seconds before raising a `TimeoutError`:

```python
try:
    async with browser_pool.acquire_context(timeout=30) as context:
        # Use context
        pass
except TimeoutError:
    logger.error("Failed to acquire browser context within timeout")
```

### Runtime Errors

- `RuntimeError("Browser pool not initialized")`: Pool must be initialized before use
- `RuntimeError("Browser pool is shutting down")`: Cannot acquire contexts during shutdown
- `RuntimeError("No healthy browser instances available")`: All browsers are unhealthy

### Automatic Fallback

If the browser pool is not initialized or unavailable, the `BrowserExecutor` automatically falls back to launching browsers per-request:

```python
# BrowserExecutor automatically handles this:
if self.browser_pool is not None and self.browser_pool._initialized:
    return await self._execute_with_pool(url, step_config, selectors)
else:
    return await self._execute_per_request(url, step_config, selectors)
```

## Performance Considerations

### Optimal Pool Size

- **Small Pool (2-3 browsers)**: Lower memory usage, suitable for light workloads
- **Medium Pool (5-10 browsers)**: Balanced performance for moderate concurrent requests
- **Large Pool (10+ browsers)**: High concurrency, requires significant memory

### Memory Usage

Each browser instance consumes approximately:
- Chromium: ~50-100 MB per browser
- Firefox: ~60-120 MB per browser
- WebKit: ~40-80 MB per browser

Plus ~10-20 MB per active context.

### Context Limits

The `browser_max_contexts_per_browser` setting controls how many contexts each browser can create. Higher values allow more concurrency but increase memory usage per browser.

## Troubleshooting

### Pool Initialization Fails

Check logs for:
```
browser_pool_initialization_failed_on_startup
```

Common causes:
- Playwright not installed: Run `playwright install`
- Insufficient system resources
- Port conflicts

### Contexts Not Available

Check metrics:
```
browser_pool_contexts_available == 0
```

Solutions:
- Increase `BROWSER_POOL_SIZE`
- Increase `BROWSER_MAX_CONTEXTS_PER_BROWSER`
- Review slow requests blocking contexts

### Unhealthy Browsers

Check health status:
```python
health = await browser_pool.health_check()
if health["unhealthy_browsers"] > 0:
    logger.error("Unhealthy browsers detected", health=health)
```

The pool automatically marks browsers as unhealthy and retries health checks periodically.

## Testing

Run browser pool tests:

```bash
# Unit tests only
uv run pytest tests/unit/test_browser_pool.py -v

# With coverage
uv run pytest tests/unit/test_browser_pool.py --cov=crawler.services.browser_pool --cov-report=html
```

## Implementation Details

### Thread Safety

The pool uses `asyncio.Lock` for thread-safe operations:
- Browser instance selection
- Context count updates
- Health status updates

### Semaphore-based Concurrency

A semaphore limits total contexts across all browsers:
```python
self._context_semaphore = asyncio.Semaphore(
    self.pool_size * self.max_contexts_per_browser
)
```

This ensures the pool never exceeds capacity.

### Health Check Loop

Health checks run in a background task:
- Checks browser connectivity
- Creates/closes test contexts
- Updates health metrics
- Runs every `browser_health_check_interval` seconds

### Guard Pattern

The code uses guard patterns for safety:
```python
# Guard: pool not initialized
if not self._initialized:
    raise RuntimeError("Browser pool not initialized")

# Guard: pool shutting down
if self._shutting_down:
    raise RuntimeError("Browser pool is shutting down")
```

## Future Enhancements

Potential improvements:
- [ ] Browser instance recreation when unhealthy
- [ ] Dynamic pool sizing based on load
- [ ] Per-browser-type pools (separate chromium/firefox pools)
- [ ] Browser launch options (headless, proxy, user-agent)
- [ ] Screenshot and HAR capture support
- [ ] Anti-detection measures integration
