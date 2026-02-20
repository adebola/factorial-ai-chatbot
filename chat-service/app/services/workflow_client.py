import asyncio
import aiohttp
import os
import redis.asyncio as aioredis
from typing import Dict, Any, Optional
from ..core.logging_config import get_logger

logger = get_logger("workflow_client")


class WorkflowClient:
    """Client for communicating with the workflow service"""

    _session: Optional[aiohttp.ClientSession] = None
    _redis: Optional[aioredis.Redis] = None

    def __init__(self, api_key: str = None):
        self.workflow_service_url = os.environ.get("WORKFLOW_SERVICE_URL", "http://localhost:8002")
        self.api_base = f"{self.workflow_service_url}/api/v1"
        self.api_key = api_key  # Tenant API key for service-to-service auth

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

    async def has_workflows(self, tenant_id: str) -> bool:
        """
        Check if a tenant has any active workflows, using Redis cache.

        Cache strategy:
        - Redis key: workflow:has_workflows:{tenant_id}
        - Value: "1" (has workflows) or "0" (no workflows)
        - TTL: 300s (5 minutes) as safety net
        - Invalidated instantly via RabbitMQ when workflows change
        """
        cache_key = f"workflow:has_workflows:{tenant_id}"
        try:
            r = await self._get_redis()
            cached = await r.get(cache_key)
            if cached is not None:
                result = cached == "1"
                logger.info(f"has_workflows cache hit: key={cache_key}, cached={cached}, result={result}")
                return result
        except Exception as e:
            logger.warning(f"Redis cache check failed for has_workflows: {e}")

        # Cache miss — call workflow service
        logger.info(f"has_workflows cache miss for {tenant_id}, calling workflow service")
        try:
            session = await self._get_session()
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with session.get(
                f"{self.api_base}/workflows/exists",
                params={"tenant_id": tenant_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=3.0)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    exists = result.get("exists", False)
                    logger.info(f"has_workflows HTTP result for {tenant_id}: exists={exists}, caching {'1' if exists else '0'}")

                    # Cache the result with 5-minute TTL
                    try:
                        r = await self._get_redis()
                        await r.setex(cache_key, 300, "1" if exists else "0")
                    except Exception as e:
                        logger.warning(f"Failed to cache has_workflows result: {e}")

                    return exists
                else:
                    logger.warning(
                        f"Workflow exists check returned {response.status}",
                        extra={"tenant_id": tenant_id}
                    )
                    # On error, assume workflows might exist to avoid skipping
                    return True

        except Exception as e:
            logger.warning(
                f"Failed to check workflow existence: {e}",
                extra={"tenant_id": tenant_id}
            )
            # On error, assume workflows might exist to avoid skipping
            return True

    async def check_triggers(
        self,
        tenant_id: str,
        message: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check if message should trigger any workflows for the tenant"""

        try:
            payload = {
                "tenant_id": tenant_id,
                "message": message,
                "session_id": session_id,
                "user_context": user_context or {}
            }

            # Prepare headers with API key if available
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            session = await self._get_session()
            logger.info(f"Calling workflow service: {self.api_base}/triggers/check with payload: {payload}")
            async with session.post(
                f"{self.api_base}/triggers/check",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as response:
                logger.info(f"Workflow service response status: {response.status}")
                if response.status == 200:
                    result = await response.json()

                    logger.info(
                        "Workflow trigger check completed",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        triggered=result.get("triggered", False),
                        workflow_id=result.get("workflow_id"),
                        workflow_name=result.get("workflow_name")
                    )

                    return result
                else:
                    logger.warning(
                        "Workflow service returned error",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        status_code=response.status,
                        response_text=await response.text()
                    )
                    return {"triggered": False}

        except asyncio.TimeoutError:
            logger.warning(
                "Workflow service timeout",
                tenant_id=tenant_id,
                session_id=session_id,
                timeout_seconds=5.0
            )
            return {"triggered": False}

        except Exception as e:
            logger.error(
                "Failed to check workflow triggers",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e))
            return {"triggered": False}

    async def start_workflow_execution(
        self,
        tenant_id: str,
        workflow_id: str,
        session_id: str,
        initial_variables: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start a workflow execution"""

        try:
            context = {}
            if user_message:
                context["triggering_message"] = user_message

            payload = {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "session_id": session_id,
                "initial_variables": initial_variables or {},
                "context": context
            }

            # Prepare headers with API key if available
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            session = await self._get_session()
            async with session.post(
                f"{self.api_base}/executions/start",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10.0)
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    logger.info(
                        "Workflow execution started",
                        tenant_id=tenant_id,
                        workflow_id=workflow_id,
                        session_id=session_id,
                        execution_id=result.get("execution_id")
                    )

                    return result
                else:
                    logger.error(
                        "Failed to start workflow execution",
                        tenant_id=tenant_id,
                        workflow_id=workflow_id,
                        session_id=session_id,
                        status_code=response.status,
                        response_text=await response.text()
                    )
                    return {"error": "Failed to start workflow execution"}

        except Exception as e:
            logger.error(
                "Error starting workflow execution",
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                session_id=session_id,
                error=str(e))
            return {"error": str(e)}

    async def execute_workflow_step(
        self,
        tenant_id: str,
        session_id: str,
        execution_id: str,
        user_input: Optional[str] = None,
        user_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute the next workflow step"""

        try:
            payload = {
                "execution_id": execution_id,
                "session_id": session_id,
                "user_input": user_input,
                "user_choice": user_choice
            }

            # Prepare headers with API key if available
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            session = await self._get_session()
            async with session.post(
                f"{self.api_base}/executions/step",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10.0)
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    logger.info(
                        "Workflow step executed",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        step_type=result.get("step_type"),
                        completed=result.get("completed", False)
                    )

                    return result
                else:
                    logger.error(
                        "Failed to execute workflow step",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        status_code=response.status,
                        response_text=await response.text()
                    )
                    return {"error": "Failed to execute workflow step"}

        except Exception as e:
            logger.error(
                "Error executing workflow step",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e))
            return {"error": str(e)}

    async def get_session_workflow_state(
        self,
        tenant_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get current workflow state for a session"""

        try:
            # Prepare headers with API key if available
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            session = await self._get_session()
            async with session.get(
                f"{self.api_base}/executions/session/{session_id}/state",
                params={"tenant_id": tenant_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    logger.debug(
                        "Retrieved workflow state",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        has_active_workflow=bool(result.get("workflow_id"))
                    )

                    return result
                elif response.status == 404:
                    # No active workflow for this session
                    return None
                else:
                    logger.warning(
                        "Failed to get workflow state",
                        tenant_id=tenant_id,
                        session_id=session_id,
                        status_code=response.status
                    )
                    return None

        except Exception as e:
            logger.error(
                "Error getting workflow state",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e))
            return None
