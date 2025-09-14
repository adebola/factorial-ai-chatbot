import json
import redis
from typing import Optional, Dict, Any
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis cache service for tenant data (read-only).
    This service only READS from cache - the authorization server is responsible
    for writing to cache to ensure data consistency.
    """

    def __init__(self):
        import os
        self.redis_client = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)
        self.cache_ttl = 300  # 5 minutes cache TTL (not used for writing, only for reference)
        
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