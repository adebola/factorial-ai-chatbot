"""
Client for fetching tenant data from the authorization server with Redis caching.
"""
import os
import json
import base64
import logging
from typing import Dict, Any, Optional

import httpx
import redis

logger = logging.getLogger(__name__)


class TenantClient:
    """Fetches tenant data from authorization server with Redis cache."""

    def __init__(self):
        self.auth_server_url = os.environ.get(
            "AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth"
        )
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    def _get_cache_key(self, lookup_type: str, value: str) -> str:
        """Generate Redis cache key."""
        return f"tenant:{lookup_type}:{value}"

    async def _get_cached_tenant(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Read from Redis cache."""
        if not self.redis_client:
            return None
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Redis cache read error: {e}")
        return None

    async def _fetch_tenant_from_auth_server(
        self, endpoint: str, params: Dict[str, str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch tenant from authorization server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.auth_server_url}{endpoint}",
                    params=params,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"Auth server returned {response.status_code}")
                    return None
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to auth server: {e}")
            return None

    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Fetch tenant by ID (cache then auth server)."""
        cache_key = self._get_cache_key("id", tenant_id)
        cached = await self._get_cached_tenant(cache_key)
        if cached:
            return cached
        return await self._fetch_tenant_from_auth_server(f"/api/v1/tenants/{tenant_id}")

    async def get_tenant_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Fetch tenant by API key."""
        # Validate this looks like an API key, not a JWT
        if api_key and api_key.count('.') >= 2:
            logger.warning("JWT token passed as API key")
            return None

        cache_key = self._get_cache_key("api_key", api_key)
        cached = await self._get_cached_tenant(cache_key)
        if cached:
            return cached
        return await self._fetch_tenant_from_auth_server(
            "/api/v1/tenants/by-api-key", params={"api_key": api_key}
        )

    async def get_tenant_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Extract tenant_id from JWT and fetch tenant."""
        try:
            # Decode JWT payload without verification to get tenant_id
            payload_segment = token.split('.')[1]
            payload_segment += '=' * (4 - len(payload_segment) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_segment))
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return await self.get_tenant_by_id(tenant_id)
        except Exception as e:
            logger.error(f"Failed to decode token for tenant lookup: {e}")
        return None
