import os
import json
import logging
from typing import Optional, Dict, Any

import httpx
import redis

from ..core.config import settings

logger = logging.getLogger(__name__)


class TenantClient:
    """
    Client for fetching tenant data from onboarding service with Redis caching
    """
    
    def __init__(self):
        self.redis_client = redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
        self.onboarding_service_url = os.environ['ONBOARDING_SERVICE_URL']
        self.cache_ttl = 300  # 5 minutes cache TTL
        
    def _get_cache_key(self, key_type: str, value: str) -> str:
        """Generate Redis cache key"""
        return f"tenant:{key_type}:{value}"
    
    async def _fetch_tenant_from_onboarding_service(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Fetch tenant data from the onboarding service"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.onboarding_service_url}/api/v1{endpoint}")
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"Error fetching tenant from onboarding service: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching tenant: {e.response.status_code}")
            return None
    
    def _cache_tenant(self, tenant_data: Dict[str, Any]) -> None:
        """Cache tenant data by ID and API key"""
        if not tenant_data:
            return
            
        tenant_json = json.dumps(tenant_data)
        tenant_id = tenant_data.get('id')
        api_key = tenant_data.get('api_key')
        
        if tenant_id:
            cache_key_id = self._get_cache_key('id', tenant_id)
            self.redis_client.setex(cache_key_id, self.cache_ttl, tenant_json)
            
        if api_key:
            cache_key_api = self._get_cache_key('api_key', api_key)
            self.redis_client.setex(cache_key_api, self.cache_ttl, tenant_json)
    
    def _get_cached_tenant(self, key_type: str, value: str) -> Optional[Dict[str, Any]]:
        """Get tenant from Redis cache"""
        try:
            cache_key = self._get_cache_key(key_type, value)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error reading from Redis cache: {e}")
        return None
    
    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID with caching"""
        # Check cache first
        cached_tenant = self._get_cached_tenant('id', tenant_id)
        if cached_tenant:
            logger.debug(f"Cache hit for tenant ID: {tenant_id}")
            return cached_tenant
        
        # Fetch from onboarding service
        logger.debug(f"Cache miss for tenant ID: {tenant_id}, fetching from onboarding service")
        tenant_data = await self._fetch_tenant_from_onboarding_service(f"/tenants/{tenant_id}/public")
        
        if tenant_data:
            self._cache_tenant(tenant_data)
            
        return tenant_data
    
    async def get_tenant_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get tenant by API key with caching"""
        
        # Validate that this is not a JWT token (common mistake)
        if api_key and '.' in api_key and len(api_key.split('.')) == 3:
            logger.warning(f"JWT token detected instead of API key: {api_key[:20]}...")
            logger.warning("Use get_tenant_by_token() method for JWT tokens!")
            logger.warning("Or extract the 'api_key' field from your JWT payload and use that instead.")
            return None
        
        # Check cache first
        cached_tenant = self._get_cached_tenant('api_key', api_key)
        if cached_tenant:
            logger.debug(f"Cache hit for API key: {api_key[:20]}...")
            return cached_tenant
        
        # Fetch from onboarding service using the API key lookup endpoint
        logger.debug(f"Cache miss for API key: {api_key[:20]}..., fetching from onboarding service")
        
        # Use the dedicated API key lookup endpoint for chat widgets
        tenant_data = await self._fetch_tenant_from_onboarding_service(f"/tenants/lookup-by-api-key?api_key={api_key}")
        
        if tenant_data:
            # Cache the result by tenant_id and api_key
            self._cache_tenant(tenant_data)
        else:
            logger.info(f"No tenant found for API key: {api_key[:20]}...")
            
        return tenant_data
    
    async def get_tenant_by_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get tenant by JWT access token with caching"""
        
        # Validate that this looks like a JWT token
        if not access_token or '.' not in access_token or len(access_token.split('.')) != 3:
            logger.warning(f"Invalid JWT token format: {access_token[:20] if access_token else 'None'}...")
            return None
        
        # For JWT tokens, we can't really cache by the token itself since it expires
        # Instead, we'll let the lookup endpoint handle the caching by tenant_id
        logger.debug(f"Fetching tenant by JWT token: {access_token[:20]}...")
        
        # Use the lookup endpoint that expects access tokens
        tenant_data = await self._fetch_tenant_from_onboarding_service(f"/tenants/lookup?access_token={access_token}")
        
        if tenant_data:
            # Cache the result by tenant_id and api_key
            self._cache_tenant(tenant_data)
        else:
            logger.info(f"No tenant found for access token: {access_token[:20]}...")
            
        return tenant_data
    
    def invalidate_tenant_cache(self, tenant_id: str = None, api_key: str = None) -> None:
        """Invalidate tenant cache"""
        try:
            if tenant_id:
                cache_key = self._get_cache_key('id', tenant_id)
                self.redis_client.delete(cache_key)
                
            if api_key:
                cache_key = self._get_cache_key('api_key', api_key)
                self.redis_client.delete(cache_key)
                
            logger.debug(f"Invalidated cache for tenant ID: {tenant_id}, API key: {api_key[:20] if api_key else None}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")