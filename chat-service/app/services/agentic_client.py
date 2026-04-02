"""
Generic client for routing messages to agentic services.

Replaces the hardcoded ObservabilityClient with a data-driven approach:
- Checks billing service for the tenant's active agentic service assignment
- Caches the result in Redis (5-minute TTL)
- Matches messages against keyword triggers from the service config
- Routes matching messages to the agentic service's query endpoint
- Fail-open: falls through to workflow/RAG on any error
"""
import asyncio
import json
import aiohttp
import os
import redis.asyncio as aioredis
from typing import Dict, Any, Optional, List
from ..core.logging_config import get_logger

logger = get_logger("agentic_client")

CACHE_TTL_SECONDS = 300  # 5 minutes


class AgenticServiceClient:
    """Generic client for routing messages to tenant-specific agentic services."""

    _session: Optional[aiohttp.ClientSession] = None
    _redis: Optional[aioredis.Redis] = None

    def __init__(self, api_key: str = None):
        self.billing_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
        self.api_key = api_key

    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            connector = aiohttp.TCPConnector(limit=10)
            cls._session = aiohttp.ClientSession(connector=connector)
        return cls._session

    @classmethod
    async def _get_redis(cls) -> aioredis.Redis:
        if cls._redis is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            cls._redis = aioredis.from_url(redis_url, decode_responses=True)
        return cls._redis

    @classmethod
    async def close(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None
        if cls._redis:
            await cls._redis.close()
            cls._redis = None

    # ── Service discovery ──

    async def get_active_service(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get the tenant's active agentic service (if any). Returns service config or None.

        Cached in Redis with 5-minute TTL. Fail-open: returns None on error.
        """
        cache_key = f"agentic:active:{tenant_id}"

        # Check cache first
        try:
            r = await self._get_redis()
            cached = await r.get(cache_key)
            if cached is not None:
                if cached == "none":
                    return None
                result = json.loads(cached)
                logger.debug("Agentic service cache hit", tenant_id=tenant_id,
                             service_key=result.get("service_key"))
                return result
        except Exception as e:
            logger.warning("Redis cache check failed for agentic service", error=str(e))

        # Cache miss — query billing service
        try:
            session = await self._get_session()
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with session.get(
                f"{self.billing_url}/api/v1/restrictions/check/active-agentic/{tenant_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=3.0)
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    if not data.get("has_service"):
                        # No agentic service — cache the negative result
                        await self._cache_result(cache_key, "none")
                        return None

                    service_info = {
                        "service_key": data["service_key"],
                        "service_name": data.get("service_name"),
                        "base_url": data["base_url"],
                        "config": data.get("config") or {},
                    }

                    logger.info("Agentic service found for tenant",
                                tenant_id=tenant_id, service_key=service_info["service_key"])
                    await self._cache_result(cache_key, json.dumps(service_info))
                    return service_info
                else:
                    logger.warning("Billing service returned non-200 for agentic check",
                                   tenant_id=tenant_id, status=response.status)
                    return None

        except Exception as e:
            logger.warning("Failed to check agentic service for tenant", tenant_id=tenant_id, error=str(e))
            return None

    async def _cache_result(self, key: str, value: str):
        try:
            r = await self._get_redis()
            await r.setex(key, CACHE_TTL_SECONDS, value)
        except Exception as e:
            logger.warning("Failed to cache agentic service result", error=str(e))

    # ── Trigger matching ──

    def matches_triggers(self, message: str, service_info: Dict[str, Any]) -> bool:
        """Check if message matches the service's keyword triggers.

        Uses simple case-insensitive word matching against config["triggers"].
        Returns True if ANY trigger keyword is found in the message.
        """
        triggers: List[str] = service_info.get("config", {}).get("triggers", [])
        if not triggers:
            # No triggers configured — route all messages to this service
            return True

        message_lower = message.lower()
        for trigger in triggers:
            if trigger.lower() in message_lower:
                return True
        return False

    # ── Query routing ──

    async def query_service(
        self,
        service_info: Dict[str, Any],
        tenant_id: str,
        session_id: str,
        message: str,
        conversation_history: list = None,
        access_token: str = None,
    ) -> Dict[str, Any]:
        """Forward query to the agentic service and return response.

        Uses base_url from the service model and query_endpoint from the config.
        Falls back gracefully on timeout or error.
        """
        base_url = service_info["base_url"]
        config = service_info.get("config", {})
        query_endpoint = config.get("query_endpoint", "/api/v1/query")
        timeout = config.get("timeout_seconds", 120)
        service_key = service_info.get("service_key", "unknown")

        url = f"{base_url}{query_endpoint}"

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
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(
                        "Agentic service query completed",
                        tenant_id=tenant_id,
                        service_key=service_key,
                        tool_calls=len(result.get("tool_calls", []))
                    )
                    return result
                else:
                    error_text = await response.text()
                    logger.error(
                        "Agentic service query failed",
                        tenant_id=tenant_id,
                        service_key=service_key,
                        status=response.status,
                        error=error_text[:500]
                    )
                    return {
                        "response": f"Service query failed ({service_key}): {error_text[:200]}",
                        "tool_calls": [],
                    }

        except asyncio.TimeoutError:
            logger.warning("Agentic service query timed out",
                           tenant_id=tenant_id, service_key=service_key, timeout=timeout)
            return {
                "response": "The query timed out. Please try a more specific question.",
                "tool_calls": [],
            }

        except Exception as e:
            logger.error("Agentic service query error",
                         tenant_id=tenant_id, service_key=service_key, error=str(e))
            return {
                "response": f"Service error: {str(e)[:200]}",
                "tool_calls": [],
            }
