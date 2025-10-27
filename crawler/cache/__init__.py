"""Cache package.

Provides Redis connection management and caching services.

## Usage

```python
from crawler.cache import get_redis
from crawler.services.redis_cache import URLDeduplicationCache

async def my_endpoint(redis = Depends(get_redis)):
    # Use redis client directly
    await redis.ping()

    # Or pass to service classes
    cache = URLDeduplicationCache(redis)
    await cache.set(url_hash, data)
```
"""

from .session import get_redis, redis_pool

__all__ = [
    "get_redis",
    "redis_pool",
]
