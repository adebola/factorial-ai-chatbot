"""
Client for communicating with the observability service.
Follows the same pattern as workflow_client.py: shared session, Redis cache, fail-open.
"""
import asyncio
import aiohttp
import os
import redis.asyncio as aioredis
from typing import Dict, Any, Optional
from ..core.logging_config import get_logger

logger = get_logger("observability_client")


class ObservabilityClient:
    """Client for communicating with the observability service."""

    _session: Optional[aiohttp.ClientSession] = None
    _redis: Optional[aioredis.Redis] = None

    def __init__(self, api_key: str = None):
        self.service_url = os.environ.get("OBSERVABILITY_SERVICE_URL", "http://localhost:8006")
        self.api_base = f"{self.service_url}/api/v1/observe"
        self.api_key = api_key

    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        """Get or create a shared aiohttp session with connection pooling."""
        if cls._session is None or cls._session.closed:
            connector = aiohttp.TCPConnector(limit=10)
            cls._session = aiohttp.ClientSession(connector=connector)
        return cls._session

    @classmethod
    async def _get_redis(cls) -> aioredis.Redis:
        """Get or create a shared async Redis client."""
        if cls._redis is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            cls._redis = aioredis.from_url(redis_url, decode_responses=True)
        return cls._redis

    @classmethod
    async def close(cls):
        """Close the shared aiohttp session and Redis client. Call during app shutdown."""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None
        if cls._redis:
            await cls._redis.close()
            cls._redis = None

    async def is_observability_tenant(self, tenant_id: str) -> bool:
        """
        Check if a tenant is in observability mode, using Redis cache.

        Cache strategy:
        - Redis key: observability:enabled:{tenant_id}
        - Value: "1" (observability mode) or "0" (not observability)
        - TTL: 300s (5 minutes)
        - Fail-open: returns False on error (falls through to RAG)
        """
        cache_key = f"observability:enabled:{tenant_id}"
        try:
            r = await self._get_redis()
            cached = await r.get(cache_key)
            if cached is not None:
                result = cached == "1"
                logger.info(f"is_observability_tenant cache hit: tenant={tenant_id}, result={result}")
                return result
        except Exception as e:
            logger.warning(f"Redis cache check failed for observability tenant: {e}")

        # Cache miss — check tenant settings via onboarding/auth service
        # For now, check if the observability service has backends configured for this tenant
        try:
            session = await self._get_session()
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with session.get(
                f"{self.api_base}/backends",
                params={"tenant_id": tenant_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=3.0)
            ) as response:
                if response.status == 200:
                    backends = await response.json()
                    # Tenant has observability if they have active backends configured
                    has_backends = len(backends) > 0
                    logger.info(f"is_observability_tenant HTTP result for {tenant_id}: {has_backends}")

                    # Cache the result
                    try:
                        r = await self._get_redis()
                        await r.setex(cache_key, 300, "1" if has_backends else "0")
                    except Exception as e:
                        logger.warning(f"Failed to cache observability tenant result: {e}")

                    return has_backends
                elif response.status == 401:
                    # Auth required - service might not be up, fail-open to RAG
                    return False
                else:
                    logger.warning(f"Observability backend check returned {response.status}")
                    return False

        except Exception as e:
            logger.warning(f"Failed to check observability tenant status: {e}")
            # Fail-open: fall through to RAG
            return False

    async def query(
        self,
        tenant_id: str,
        session_id: str,
        message: str,
        conversation_history: list = None,
        access_token: str = None
    ) -> Dict[str, Any]:
        """
        Send a query to the observability agent service.

        Returns dict with 'response', 'tool_calls', 'session_id', 'query_id'.
        """
        try:
            payload = {
                "tenant_id": tenant_id,
                "session_id": session_id,
                "message": message,
            }
            if conversation_history:
                payload["conversation_history"] = conversation_history

            headers = {"Content-Type": "application/json"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            elif self.api_key:
                headers["X-API-Key"] = self.api_key

            session = await self._get_session()
            async with session.post(
                f"{self.api_base}/query",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60.0)  # Agent may chain multiple tools
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(
                        "Observability query completed",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        tool_calls=len(result.get("tool_calls", []))
                    )
                    return result
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Observability query failed: {response.status}",
                        tenant_id=tenant_id,
                        response_text=error_text[:500]
                    )
                    return {
                        "response": f"Observability query failed: {error_text[:200]}",
                        "tool_calls": [],
                        "session_id": session_id,
                        "query_id": None
                    }

        except asyncio.TimeoutError:
            logger.warning("Observability query timed out", tenant_id=tenant_id)
            return {
                "response": "The observability query timed out. Please try a more specific question.",
                "tool_calls": [],
                "session_id": session_id,
                "query_id": None
            }

        except Exception as e:
            logger.error(f"Observability query error: {e}", tenant_id=tenant_id)
            raise
