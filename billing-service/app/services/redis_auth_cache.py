"""
Redis-based token validation cache for improved performance across all services.
Provides shared caching that all microservices can use, avoiding duplicate validations.
"""
import os
import json
import time
import redis
import hashlib
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class CachedTokenInfo:
    """Token information stored in Redis"""
    token_info: Dict[str, Any]
    cached_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None  # Absolute expiration time

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "token_info": self.token_info,
            "cached_at": self.cached_at,
            "expires_at": self.expires_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedTokenInfo':
        """Create from dictionary"""
        return cls(
            token_info=data["token_info"],
            cached_at=data.get("cached_at", time.time()),
            expires_at=data.get("expires_at")
        )


class RedisTokenCache:
    """
    Redis-based cache for token validation results.
    Shared across all microservices to reduce duplicate validation work.

    Features:
    - Shared cache across all services
    - Automatic expiration based on token exp claim
    - TTL-based cache management
    - Consistent hashing for token keys
    - Built-in metrics tracking
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 60,
        key_prefix: str = "auth:token:",
        metrics_window: int = 3600  # 1 hour metrics window
    ):
        """
        Initialize the Redis token cache.

        Args:
            redis_url: Redis connection URL (defaults to REDIS_URL env var)
            default_ttl: Default TTL in seconds when token doesn't have exp claim
            key_prefix: Prefix for all cache keys
            metrics_window: Time window for metrics tracking in seconds
        """
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.metrics_window = metrics_window

        try:
            # Create Redis client with connection pool
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis token cache at {self.redis_url}")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Error initializing Redis cache: {e}")
            raise

    def _generate_cache_key(self, token: str) -> str:
        """
        Generate a consistent cache key for a token.
        Uses SHA256 hash for security and consistency.
        """
        # Use SHA256 hash of the full token for security
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        return f"{self.key_prefix}{token_hash}"

    def _calculate_ttl(self, token_info: Dict[str, Any]) -> int:
        """
        Calculate TTL based on token expiration.

        Args:
            token_info: The decoded token claims

        Returns:
            TTL in seconds
        """
        now = time.time()
        exp = token_info.get("exp")

        if exp:
            # Calculate remaining time until expiration
            remaining = int(exp - now)
            # For very short-lived tokens, don't subtract the buffer
            if remaining <= 10:
                # For tokens expiring in 10 seconds or less, use exact remaining time
                return max(1, remaining)  # At least 1 second
            else:
                # For longer-lived tokens, subtract a small buffer for clock skew
                # and cap at default TTL to prevent excessive cache times
                return max(0, min(remaining - 5, self.default_ttl))
        else:
            # No expiration claim, use default TTL
            return self.default_ttl

    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get cached token info if available and not expired.

        Args:
            token: The JWT token to look up

        Returns:
            Cached token info or None if not found/expired
        """
        try:
            cache_key = self._generate_cache_key(token)

            # Get from Redis
            cached_json = self.redis_client.get(cache_key)

            if cached_json:
                # Parse cached data
                cached_data = json.loads(cached_json)
                cached_info = CachedTokenInfo.from_dict(cached_data)

                # Check if token has expired based on exp claim
                now = time.time()
                if cached_info.expires_at and now > cached_info.expires_at:
                    # Token expired, remove from cache
                    self.redis_client.delete(cache_key)
                    self._increment_metric("misses")
                    logger.debug(f"Token expired in cache, removed: {cache_key[-8:]}")
                    return None

                # Cache hit
                self._increment_metric("hits")
                logger.debug(f"Cache hit for token: {cache_key[-8:]}")
                return cached_info.token_info
            else:
                # Cache miss
                self._increment_metric("misses")
                return None

        except redis.RedisError as e:
            logger.error(f"Redis error during get: {e}")
            self._increment_metric("errors")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cache: {e}")
            self.redis_client.delete(cache_key)
            return None
        except Exception as e:
            logger.error(f"Unexpected error during cache get: {e}")
            return None

    async def set(self, token: str, token_info: Dict[str, Any]) -> bool:
        """
        Cache token validation result.

        Args:
            token: The JWT token
            token_info: The decoded JWT claims or introspection result

        Returns:
            True if successfully cached, False otherwise
        """
        try:
            cache_key = self._generate_cache_key(token)

            # Calculate TTL and expiration
            ttl = self._calculate_ttl(token_info)
            if ttl <= 0:
                logger.debug("Token already expired, not caching")
                return False

            # Create cached info
            expires_at = token_info.get("exp")
            cached_info = CachedTokenInfo(
                token_info=token_info,
                expires_at=expires_at
            )

            # Store in Redis with TTL
            cached_json = json.dumps(cached_info.to_dict())
            self.redis_client.setex(
                cache_key,
                ttl,
                cached_json
            )

            # Update metrics
            self._increment_metric("sets")
            logger.debug(f"Cached token validation result: {cache_key[-8:]} (TTL: {ttl}s)")
            return True

        except redis.RedisError as e:
            logger.error(f"Redis error during set: {e}")
            self._increment_metric("errors")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during cache set: {e}")
            return False

    async def invalidate(self, token: str) -> bool:
        """
        Invalidate a cached token.

        Args:
            token: The JWT token to invalidate

        Returns:
            True if token was in cache and removed, False otherwise
        """
        try:
            cache_key = self._generate_cache_key(token)
            result = self.redis_client.delete(cache_key)

            if result:
                self._increment_metric("invalidations")
                logger.debug(f"Invalidated token: {cache_key[-8:]}")

            return bool(result)

        except redis.RedisError as e:
            logger.error(f"Redis error during invalidate: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during invalidate: {e}")
            return False

    def _increment_metric(self, metric_type: str) -> None:
        """
        Increment a metric counter.

        Args:
            metric_type: Type of metric (hits, misses, sets, errors, invalidations)
        """
        try:
            # Use Redis to track metrics with automatic expiration
            metric_key = f"{self.key_prefix}metrics:{metric_type}"

            # Increment counter
            self.redis_client.incr(metric_key)

            # Set expiration if this is a new key
            self.redis_client.expire(metric_key, self.metrics_window)

        except redis.RedisError:
            # Don't let metric tracking failures affect main operations
            pass


# Global instance for easy import
# Services should import this or create their own instance
redis_token_cache = RedisTokenCache()
