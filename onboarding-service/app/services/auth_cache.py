"""
Token validation cache for improved performance.
Caches decoded JWT claims to avoid repeated validation.
"""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class CachedToken:
    """Cached token information"""
    token_info: Dict[str, Any]
    cached_at: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int = 60) -> bool:
        """Check if cached entry has expired"""
        # Check both cache TTL and token expiration
        now = time.time()

        # Check cache TTL
        if now - self.cached_at > ttl_seconds:
            return True

        # Check token expiration (if available)
        exp = self.token_info.get("exp")
        if exp and now > exp:
            return True

        return False


class TokenValidationCache:
    """
    In-memory cache for token validation results.
    Reduces latency by caching decoded JWT claims.
    Works with both local JWT validation and introspection.
    """

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        """
        Initialize the token cache.

        Args:
            ttl_seconds: Time to live for cached entries (default 60 seconds)
            max_size: Maximum number of tokens to cache (default 1000)
        """
        self._cache: Dict[str, CachedToken] = {}
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get cached token info if available and not expired.

        Args:
            token: The JWT token to look up

        Returns:
            Cached token info or None if not found/expired
        """
        async with self._lock:
            # Extract a shorter key from token (last 20 chars are usually enough for uniqueness)
            cache_key = token[-20:] if len(token) > 20 else token

            cached = self._cache.get(cache_key)
            if cached and not cached.is_expired(self._ttl_seconds):
                self._hits += 1
                logger.debug(f"Cache hit for token (hit rate: {self.hit_rate:.1%})")
                return cached.token_info

            # Remove expired entry if exists
            if cached:
                del self._cache[cache_key]

            self._misses += 1
            return None

    async def set(self, token: str, token_info: Dict[str, Any]) -> None:
        """
        Cache token validation result.

        Args:
            token: The JWT token
            token_info: The decoded JWT claims or introspection result
        """
        async with self._lock:
            # Evict oldest entries if cache is full
            if len(self._cache) >= self._max_size:
                # Find and remove the oldest entry
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k].cached_at
                )
                del self._cache[oldest_key]
                logger.debug("Evicted oldest cache entry")

            # Store with shorter key
            cache_key = token[-20:] if len(token) > 20 else token
            self._cache[cache_key] = CachedToken(token_info)
            logger.debug(f"Cached token validation result (cache size: {len(self._cache)})")

    async def clear(self) -> None:
        """Clear all cached tokens"""
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("Token cache cleared")

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)

    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, cached in self._cache.items()
                if cached.is_expired(self._ttl_seconds)
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

            return len(expired_keys)


# Global cache instance
token_cache = TokenValidationCache(ttl_seconds=60, max_size=1000)