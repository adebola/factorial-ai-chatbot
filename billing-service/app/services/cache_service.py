import json
import redis
from typing import Optional, Dict, Any
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis cache service for tenant and plan data.

    IMPORTANT: This service is the AUTHORITATIVE cache manager for plans.
    - Plans: Onboarding service manages (read/write)
    - Tenants: Read-only (authorization server manages)
    """

    def __init__(self):
        import os
        self.redis_client = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)
        self.tenant_cache_ttl = 300  # 5 minutes for tenant data (read-only)
        self.plan_cache_ttl = 3600  # 1 hour for plan data (managed by this service)
        
    def _get_cache_key(self, key_type: str, value: str) -> str:
        """Generate Redis cache key (compatible with OAuth server format)"""
        if key_type == 'id':
            return f"tenant:{value}"
        elif key_type == 'api_key':
            return f"tenant:api:{value}"
        else:
            return f"tenant:{key_type}:{value}"
    
    # Note: cache_tenant method removed - only authorization server writes to cache
    
    def get_cached_tenant(self, key_type: str, value: str) -> Optional[Dict[str, Any]]:
        """Get tenant from Redis cache (read-only access)"""
        try:
            # For API key lookups, first get tenant ID then fetch full tenant data
            if key_type == 'api_key':
                api_cache_key = self._get_cache_key('api_key', value)
                cached_tenant_id = self.redis_client.get(api_cache_key)

                if cached_tenant_id:
                    # Found tenant ID, now get the full tenant data
                    tenant_cache_key = self._get_cache_key('id', cached_tenant_id)
                    cached_data = self.redis_client.get(tenant_cache_key)
                    if cached_data:
                        return json.loads(cached_data)
            else:
                # Direct lookup by ID or other key type
                cache_key = self._get_cache_key(key_type, value)
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error reading from Redis cache: {e}")
        return None
    
    def invalidate_tenant_cache(self, tenant_id: str = None, api_key: str = None) -> None:
        """
        Invalidate tenant cache - WARNING: This should normally only be done by the authorization server.
        Use with caution to maintain cache consistency.
        """
        logger.warning("Cache invalidation called from onboarding service - ensure authorization server is aware")
        try:
            if tenant_id:
                cache_key = self._get_cache_key('id', str(tenant_id))
                self.redis_client.delete(cache_key)

            if api_key:
                cache_key = self._get_cache_key('api_key', api_key)
                self.redis_client.delete(cache_key)

            logger.debug(f"Invalidated cache for tenant ID: {tenant_id}, API key: {api_key[:20] if api_key else None}...")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")

    # =====================================================
    # PLAN CACHE MANAGEMENT METHODS (Onboarding Service Authoritative)
    # =====================================================

    def _get_plan_cache_key(self, key_type: str, value: str = None) -> str:
        """Generate plan-specific cache keys"""
        if key_type == 'free_tier':
            return "plan:free_tier"
        elif key_type == 'all_active':
            return "plans:active"
        elif key_type == 'plan_id' and value:
            return f"plan:id:{value}"
        else:
            return f"plan:{key_type}:{value}" if value else f"plan:{key_type}"

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Generic cache get method"""
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error reading from Redis cache (key: {cache_key}): {e}")
        return None

    async def set(self, cache_key: str, data: Dict[str, Any], ttl: int = None) -> bool:
        """Generic cache set method"""
        try:
            if ttl is None:
                ttl = self.plan_cache_ttl

            serialized_data = json.dumps(data, default=str)
            result = self.redis_client.setex(cache_key, ttl, serialized_data)
            logger.debug(f"Cached data with key '{cache_key}' for {ttl} seconds")
            return bool(result)
        except Exception as e:
            logger.error(f"Error writing to Redis cache (key: {cache_key}): {e}")
            return False

    async def delete(self, cache_key: str) -> bool:
        """Generic cache delete method"""
        try:
            result = self.redis_client.delete(cache_key)
            logger.debug(f"Deleted cache key: {cache_key}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting from Redis cache (key: {cache_key}): {e}")
            return False

    # Plan-specific cache methods
    async def get_free_tier_plan(self) -> Optional[Dict[str, Any]]:
        """Get free tier plan from cache"""
        cache_key = self._get_plan_cache_key('free_tier')
        return await self.get(cache_key)

    async def cache_free_tier_plan(self, plan_data: Dict[str, Any]) -> bool:
        """Cache free tier plan data"""
        cache_key = self._get_plan_cache_key('free_tier')
        return await self.set(cache_key, plan_data, self.plan_cache_ttl)

    async def invalidate_free_tier_plan(self) -> bool:
        """Invalidate free tier plan cache"""
        cache_key = self._get_plan_cache_key('free_tier')
        return await self.delete(cache_key)

    async def get_plan_by_id(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Get specific plan by ID from cache"""
        cache_key = self._get_plan_cache_key('plan_id', plan_id)
        return await self.get(cache_key)

    async def cache_plan_by_id(self, plan_id: str, plan_data: Dict[str, Any]) -> bool:
        """Cache specific plan by ID"""
        cache_key = self._get_plan_cache_key('plan_id', plan_id)
        return await self.set(cache_key, plan_data, self.plan_cache_ttl)

    async def invalidate_plan_by_id(self, plan_id: str) -> bool:
        """Invalidate specific plan cache"""
        cache_key = self._get_plan_cache_key('plan_id', plan_id)
        return await self.delete(cache_key)

    async def get_all_active_plans(self) -> Optional[Dict[str, Any]]:
        """Get all active plans from cache"""
        cache_key = self._get_plan_cache_key('all_active')
        return await self.get(cache_key)

    async def cache_all_active_plans(self, plans_data: Dict[str, Any]) -> bool:
        """Cache all active plans"""
        cache_key = self._get_plan_cache_key('all_active')
        return await self.set(cache_key, plans_data, self.plan_cache_ttl)

    async def invalidate_all_plans_cache(self) -> bool:
        """Invalidate all plan-related cache entries"""
        try:
            # Get all plan cache keys
            plan_keys = self.redis_client.keys("plan:*")
            if plan_keys:
                self.redis_client.delete(*plan_keys)
                logger.info(f"Invalidated {len(plan_keys)} plan cache entries")
            return True
        except Exception as e:
            logger.error(f"Error invalidating all plan caches: {e}")
            return False

    async def refresh_plan_cache(self, plan_id: str = None) -> None:
        """
        Signal to refresh plan cache. This method triggers cache invalidation
        so that the next request will fetch fresh data from the database.
        """
        if plan_id:
            # Invalidate specific plan
            await self.invalidate_plan_by_id(plan_id)
            logger.info(f"Triggered cache refresh for plan: {plan_id}")
        else:
            # Invalidate all plan caches
            await self.invalidate_all_plans_cache()
            logger.info("Triggered cache refresh for all plans")