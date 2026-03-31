"""
HTTP client for billing service — checks agentic service access.

Includes Redis caching with 5-min TTL and fail-closed behavior.
"""
import json
import logging
import os
from typing import Tuple, Optional, Dict, Any

import httpx
import redis

logger = logging.getLogger(__name__)

BILLING_SERVICE_URL = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = 300  # 5 minutes

# Module-level HTTP client for connection pooling
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


def _get_redis() -> Optional[redis.Redis]:
    try:
        return redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
        return None


async def check_service_access(
    tenant_id: str, service_key: str
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Check whether a tenant has access to an agentic service.

    Returns:
        (allowed, config_dict_or_none, reason_if_denied)

    Fail-closed: returns (False, None, reason) when billing is unreachable
    and cache is empty.
    """
    cache_key = f"svc_access:{tenant_id}:{service_key}"

    # ── Try Redis cache first ──
    r = _get_redis()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                data = json.loads(cached)
                return data["allowed"], data.get("config"), data.get("reason")
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")

    # ── Call billing service ──
    url = f"{BILLING_SERVICE_URL}/api/v1/restrictions/check/service-access/{tenant_id}/{service_key}"
    try:
        client = _get_http_client()
        resp = await client.get(url)

        if resp.status_code == 200:
            data = resp.json()
            allowed = data.get("allowed", False)
            config = data.get("config")
            reason = data.get("reason")

            # Cache the result
            if r:
                try:
                    r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps({
                        "allowed": allowed,
                        "config": config,
                        "reason": reason,
                    }))
                except Exception as e:
                    logger.warning(f"Redis cache write error: {e}")

            return allowed, config, reason
        else:
            logger.error(f"Billing service returned {resp.status_code} for service access check")
            return False, None, "Billing service error"

    except httpx.RequestError as e:
        logger.error(f"Billing service unreachable: {e}")
        return False, None, "Service access check unavailable — billing service unreachable"
