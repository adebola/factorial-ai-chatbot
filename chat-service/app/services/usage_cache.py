"""
Redis Usage Cache Manager

Fast local cache for tenant chat usage limits to avoid synchronous HTTP calls
to the billing service on every message. Provides sub-millisecond limit checks
with push-based cache invalidation for accuracy.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple, Optional

import redis
import httpx

logger = logging.getLogger(__name__)


class UsageCacheManager:
    """
    Manages Redis cache for tenant chat usage limits.

    Strategy:
    - Cache usage limits with 5-minute TTL
    - Optimistic local increment after each message
    - Push-based cache invalidation when limits exceeded
    - Graceful degradation (fail open) if Redis/billing unavailable
    """

    def __init__(self):
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

        self.billing_service_url = os.environ.get(
            "BILLING_SERVICE_URL",
            "http://localhost:8004"
        )
        self.cache_ttl = int(os.environ.get("USAGE_CACHE_TTL_SECONDS", "300"))  # 5 minutes default
        self.http_timeout = float(os.environ.get("BILLING_SERVICE_TIMEOUT", "5.0"))

    def _cache_key(self, tenant_id: str) -> str:
        """Generate Redis cache key for tenant usage"""
        return f"usage:{tenant_id}"

    async def check_chat_allowed(self, tenant_id: str, api_key: str = None) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant is allowed to send chat messages.

        Fast path: Check Redis cache (~1ms)
        Slow path: Fetch from billing service if cache miss (~50-200ms)

        Args:
            tenant_id: Tenant UUID
            api_key: Optional API key for billing service auth

        Returns:
            Tuple of (allowed: bool, reason: str | None)
            - (True, None) if allowed
            - (False, "reason") if not allowed
        """
        try:
            # Fast path: Check Redis cache
            cache_key = self._cache_key(tenant_id)
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                usage_data = json.loads(cached_data)

                # Check if unlimited
                if usage_data.get("unlimited", False):
                    return (True, None)

                # Check daily limit
                daily_used = usage_data.get("daily_used", 0)
                daily_limit = usage_data.get("daily_limit", 0)

                if daily_limit > 0 and daily_used >= daily_limit:
                    return (False, f"Daily chat limit reached ({daily_used}/{daily_limit})")

                # Check monthly limit
                monthly_used = usage_data.get("monthly_used", 0)
                monthly_limit = usage_data.get("monthly_limit", 0)

                if monthly_limit > 0 and monthly_used >= monthly_limit:
                    return (False, f"Monthly chat limit reached ({monthly_used}/{monthly_limit})")

                # All checks passed
                return (True, None)

            # Slow path: Cache miss - fetch from billing service
            logger.debug(f"Cache miss for tenant {tenant_id}, fetching from billing service")
            return await self._fetch_and_cache_usage(tenant_id, api_key)

        except redis.RedisError as e:
            # Redis unavailable - fail open (allow chat to continue)
            logger.warning(f"Redis error checking usage for tenant {tenant_id}: {e}")
            return (True, None)
        except Exception as e:
            # Unexpected error - fail open
            logger.error(f"Error checking chat limit for tenant {tenant_id}: {e}", exc_info=True)
            return (True, None)

    async def _fetch_and_cache_usage(
        self,
        tenant_id: str,
        api_key: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Fetch usage from billing service and cache it.

        Args:
            tenant_id: Tenant UUID
            api_key: Tenant API key for authentication

        Returns:
            Tuple of (allowed, reason)
        """
        try:
            # Internal service-to-service call with API key authentication
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key

            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(
                    f"{self.billing_service_url}/api/v1/usage/stats/{tenant_id}",
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage", {})

                    # Build cache data structure
                    cache_data = {
                        "daily_used": usage.get("daily_chats_used", 0),
                        "daily_limit": -1,  # Will be set from plan check
                        "monthly_used": usage.get("monthly_chats_used", 0),
                        "monthly_limit": -1,
                        "unlimited": False,
                        "cached_at": datetime.now(timezone.utc).isoformat()
                    }

                    # Fetch plan limits with API key authentication
                    plan_response = await client.get(
                        f"{self.billing_service_url}/api/v1/usage/check/daily_chats",
                        headers=headers
                    )

                    if plan_response.status_code == 200:
                        plan_data = plan_response.json()
                        cache_data["daily_limit"] = plan_data.get("limit", -1)
                        cache_data["unlimited"] = plan_data.get("unlimited", False)

                    # Fetch monthly limit
                    monthly_response = await client.get(
                        f"{self.billing_service_url}/api/v1/usage/check/monthly_chats",
                        headers=headers
                    )

                    if monthly_response.status_code == 200:
                        monthly_data = monthly_response.json()
                        cache_data["monthly_limit"] = monthly_data.get("limit", -1)

                    # Cache the data
                    self._cache_usage_data(tenant_id, cache_data)

                    # Check limits
                    if cache_data["unlimited"]:
                        return (True, None)

                    if cache_data["daily_limit"] > 0 and cache_data["daily_used"] >= cache_data["daily_limit"]:
                        return (False, f"Daily chat limit reached ({cache_data['daily_used']}/{cache_data['daily_limit']})")

                    if cache_data["monthly_limit"] > 0 and cache_data["monthly_used"] >= cache_data["monthly_limit"]:
                        return (False, f"Monthly chat limit reached ({cache_data['monthly_used']}/{cache_data['monthly_limit']})")

                    return (True, None)

                elif response.status_code in [401, 403]:
                    # Authentication/authorization failed
                    return (False, "Unauthorized")
                else:
                    # Billing service error - fail open
                    logger.warning(f"Billing service returned {response.status_code} for tenant {tenant_id}")
                    return (True, None)

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching usage from billing service for tenant {tenant_id}")
            return (True, None)  # Fail open
        except httpx.ConnectError:
            logger.error(f"Cannot connect to billing service at {self.billing_service_url}")
            return (True, None)  # Fail open
        except Exception as e:
            logger.error(f"Error fetching usage from billing service: {e}", exc_info=True)
            return (True, None)  # Fail open

    def _cache_usage_data(self, tenant_id: str, cache_data: Dict[str, Any]):
        """
        Store usage data in Redis cache.

        Args:
            tenant_id: Tenant UUID
            cache_data: Usage data dictionary
        """
        try:
            cache_key = self._cache_key(tenant_id)
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(cache_data)
            )
            logger.debug(f"Cached usage data for tenant {tenant_id} (TTL: {self.cache_ttl}s)")
        except redis.RedisError as e:
            logger.warning(f"Failed to cache usage data for tenant {tenant_id}: {e}")

    def increment_local_cache(self, tenant_id: str, message_count: int = 1):
        """
        Optimistically increment cached usage counters.

        This is called after a message is sent to provide immediate feedback
        for the next message check without waiting for the billing service.

        Args:
            tenant_id: Tenant UUID
            message_count: Number of messages to increment (default 1)
        """
        try:
            cache_key = self._cache_key(tenant_id)
            cached_data = self.redis_client.get(cache_key)

            if cached_data:
                usage_data = json.loads(cached_data)
                usage_data["daily_used"] += message_count
                usage_data["monthly_used"] += message_count

                # Update cache with same TTL
                ttl = self.redis_client.ttl(cache_key)
                if ttl > 0:
                    self.redis_client.setex(cache_key, ttl, json.dumps(usage_data))
                    logger.debug(f"Incremented local cache for tenant {tenant_id}: +{message_count}")

        except redis.RedisError as e:
            logger.warning(f"Failed to increment local cache for tenant {tenant_id}: {e}")
        except Exception as e:
            logger.error(f"Error incrementing local cache: {e}", exc_info=True)

    def invalidate_cache(self, tenant_id: str):
        """
        Force invalidate cache for a tenant.

        This is called when a limit exceeded warning is received from the
        billing service, ensuring the next check fetches fresh data.

        Args:
            tenant_id: Tenant UUID
        """
        try:
            cache_key = self._cache_key(tenant_id)
            self.redis_client.delete(cache_key)
            logger.info(f"Invalidated usage cache for tenant {tenant_id}")
        except redis.RedisError as e:
            logger.warning(f"Failed to invalidate cache for tenant {tenant_id}: {e}")

    async def prefetch_for_tenant(self, tenant_id: str, api_key: str = None):
        """
        Warm the cache for a tenant (e.g., on WebSocket connect).

        This provides faster first-message experience by pre-fetching
        usage data before the user sends their first message.

        Args:
            tenant_id: Tenant UUID
            api_key: Optional API key for auth
        """
        try:
            cache_key = self._cache_key(tenant_id)

            # Check if already cached
            if self.redis_client.exists(cache_key):
                logger.debug(f"Cache already warm for tenant {tenant_id}")
                return

            # Fetch and cache
            logger.debug(f"Warming cache for tenant {tenant_id}")
            await self._fetch_and_cache_usage(tenant_id, api_key)

        except Exception as e:
            logger.warning(f"Failed to prefetch usage for tenant {tenant_id}: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache stats
        """
        try:
            # Count cached tenant keys
            usage_keys = self.redis_client.keys("usage:*")

            return {
                "cached_tenants": len(usage_keys),
                "cache_ttl_seconds": self.cache_ttl,
                "redis_connected": self.redis_client.ping()
            }
        except redis.RedisError as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {
                "cached_tenants": 0,
                "cache_ttl_seconds": self.cache_ttl,
                "redis_connected": False,
                "error": str(e)
            }


# Global cache manager instance
usage_cache = UsageCacheManager()
