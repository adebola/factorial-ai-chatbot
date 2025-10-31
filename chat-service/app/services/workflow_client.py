import aiohttp
import os
from typing import Dict, Any, Optional
from ..core.logging_config import get_logger

logger = get_logger("workflow_client")


class WorkflowClient:
    """Client for communicating with the workflow service"""

    def __init__(self, api_key: str = None):
        self.workflow_service_url = os.environ.get("WORKFLOW_SERVICE_URL", "http://localhost:8002")
        self.api_base = f"{self.workflow_service_url}/api/v1"
        self.api_key = api_key  # Tenant API key for service-to-service auth

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

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/triggers/check",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5.0)
                ) as response:
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

        except aiohttp.ClientTimeout:
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
                error=str(e),
                exc_info=True
            )
            return {"triggered": False}

    async def start_workflow_execution(
        self,
        tenant_id: str,
        workflow_id: str,
        session_id: str,
        initial_variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Start a workflow execution"""

        try:
            payload = {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "session_id": session_id,
                "initial_variables": initial_variables or {}
            }

            # Prepare headers with API key if available
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            async with aiohttp.ClientSession() as session:
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
                error=str(e),
                exc_info=True
            )
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

            async with aiohttp.ClientSession() as session:
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
                error=str(e),
                exc_info=True
            )
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

            async with aiohttp.ClientSession() as session:
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
                error=str(e),
                exc_info=True
            )
            return None