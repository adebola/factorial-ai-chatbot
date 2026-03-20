"""
Redis-based token validation cache shared across all microservices.
"""
import os
import time
import json
import hashlib
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

import redis

logger = logging.getLogger(__name__)


@dataclass
class CachedTokenInfo:
    """Container for cached token validation data."""
    token_info: Dict[str, Any]
    cached_at: float = field(default_factory=time.time)
    ttl_seconds: int = 60


class RedisTokenCache:
    """Redis-backed token validation cache."""

    def __init__(self):
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info("Redis token cache initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis token cache: {e}")
            self.redis_client = None

        self._metrics = {"hits": 0, "misses": 0, "sets": 0, "errors": 0, "invalidations": 0}

    def _cache_key(self, token: str) -> str:
        """Generate a SHA256-based cache key for a token."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return f"token_cache:{token_hash}"

    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        """Get cached token info."""
        if not self.redis_client:
            return None
        try:
            key = self._cache_key(token)
            cached = self.redis_client.get(key)
            if cached:
                self._metrics["hits"] += 1
                return json.loads(cached)
            self._metrics["misses"] += 1
            return None
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error(f"Redis cache get error: {e}")
            return None

    async def set(self, token: str, token_info: Dict[str, Any]) -> None:
        """Cache token validation result."""
        if not self.redis_client:
            return
        try:
            key = self._cache_key(token)
            # Calculate TTL based on token expiration
            exp = token_info.get("exp", 0)
            now = int(time.time())
            if exp > 0:
                remaining = exp - now
                ttl = min(remaining, 60)  # Cap at 60 seconds
                if ttl <= 0:
                    return
            else:
                ttl = 60

            self.redis_client.setex(key, int(ttl), json.dumps(token_info))
            self._metrics["sets"] += 1
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error(f"Redis cache set error: {e}")

    async def invalidate(self, token: str) -> None:
        """Remove a cached token."""
        if not self.redis_client:
            return
        try:
            key = self._cache_key(token)
            self.redis_client.delete(key)
            self._metrics["invalidations"] += 1
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error(f"Redis cache invalidate error: {e}")

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self.redis_client:
            return False
        try:
            return self.redis_client.ping()
        except Exception:
            return False

    def get_metrics(self) -> Dict[str, int]:
        """Get cache metrics."""
        return dict(self._metrics)


redis_token_cache = RedisTokenCache()
