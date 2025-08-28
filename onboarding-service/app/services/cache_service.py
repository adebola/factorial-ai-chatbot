import json
import redis
from typing import Optional, Dict, Any
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis cache service for tenant data
    """
    
    def __init__(self):
        import os
        self.redis_client = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)
        self.cache_ttl = 300  # 5 minutes cache TTL
        
    def _get_cache_key(self, key_type: str, value: str) -> str:
        """Generate Redis cache key"""
        return f"tenant:{key_type}:{value}"
    
    def cache_tenant(self, tenant_data: Dict[str, Any]) -> None:
        """Cache tenant data by ID and API key"""
        if not tenant_data:
            return
            
        tenant_json = json.dumps(tenant_data)
        tenant_id = tenant_data.get('id')
        api_key = tenant_data.get('api_key')
        
        try:
            if tenant_id:
                cache_key_id = self._get_cache_key('id', str(tenant_id))
                self.redis_client.setex(cache_key_id, self.cache_ttl, tenant_json)
                
            if api_key:
                cache_key_api = self._get_cache_key('api_key', api_key)
                self.redis_client.setex(cache_key_api, self.cache_ttl, tenant_json)
                
            logger.debug(f"Cached tenant data for ID: {tenant_id}, API key: {api_key[:20] if api_key else None}...")
        except Exception as e:
            logger.error(f"Error caching tenant data: {e}")
    
    def get_cached_tenant(self, key_type: str, value: str) -> Optional[Dict[str, Any]]:
        """Get tenant from Redis cache"""
        try:
            cache_key = self._get_cache_key(key_type, value)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error reading from Redis cache: {e}")
        return None
    
    def invalidate_tenant_cache(self, tenant_id: str = None, api_key: str = None) -> None:
        """Invalidate tenant cache"""
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