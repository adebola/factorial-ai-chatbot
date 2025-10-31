"""
HTTP Client for Billing Service API

This client provides methods to communicate with the Billing Service for:
- Checking usage limits (documents, websites, chats)
- Validating subscription status
- Enforcing plan restrictions

The client uses a fail-open strategy: if the billing service is unavailable,
it logs warnings but allows operations to proceed.
"""

import httpx
import os
from typing import Dict, Any
from fastapi import HTTPException, status
from ..core.logging_config import get_logger

logger = get_logger("billing_client")


class BillingClient:
    """
    HTTP client for communicating with the Billing Service.

    The billing service runs on port 8002 and provides REST APIs for
    subscription management, usage tracking, and limit enforcement.

    Usage:
        client = BillingClient(access_token)
        result = await client.check_usage_limit("documents")
        if not result["allowed"]:
            raise HTTPException(status_code=429, detail=result["reason"])
    """

    def __init__(self, access_token: str):
        """
        Initialize billing client with authentication token.

        Args:
            access_token: JWT Bearer token from user request
        """
        self.access_token = access_token
        self.billing_url = os.environ.get(
            "BILLING_SERVICE_URL",
            "http://localhost:8002"
        )
        logger.debug(f"Billing client initialized with URL: {self.billing_url}")

    async def check_usage_limit(self, usage_type: str) -> Dict[str, Any]:
        """
        Check if user can perform an action based on their subscription limits.

        Makes a synchronous HTTP call to the billing service to validate
        whether the tenant has remaining quota for the specified resource type.

        Args:
            usage_type: Type of usage to check. Valid values:
                - "documents" - Document upload limit
                - "websites" - Website ingestion limit
                - "daily_chats" - Daily chat message limit
                - "monthly_chats" - Monthly chat message limit

        Returns:
            Dict with keys:
                - allowed (bool): Whether action is allowed
                - usage_type (str): The type that was checked
                - current_usage (int): Current usage count
                - limit (int): Max allowed (-1 = unlimited)
                - remaining (int): Remaining quota (-1 = unlimited)
                - unlimited (bool): Whether resource is unlimited
                - reason (str|None): Reason if not allowed

        Examples:
            >>> client = BillingClient(token)
            >>> result = await client.check_usage_limit("documents")
            >>> if result["allowed"]:
            >>>     # Proceed with document upload
            >>> else:
            >>>     # Return error: result["reason"]

        Raises:
            HTTPException: If billing service returns 401 (authentication failed)

        Note:
            This method uses a fail-open strategy. If the billing service is
            unavailable (timeout, connection error, 5xx), it returns
            {"allowed": True} to avoid blocking operations. All failures are
            logged for monitoring.
        """
        endpoint = f"{self.billing_url}/api/v1/usage/check/{usage_type}"

        try:
            async with httpx.AsyncClient() as client:
                logger.debug(
                    "Checking usage limit",
                    usage_type=usage_type,
                    endpoint=endpoint
                )

                response = await client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    timeout=5.0  # Fast timeout - fail fast
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        "Usage limit check completed",
                        usage_type=usage_type,
                        allowed=data.get("allowed"),
                        current_usage=data.get("current_usage"),
                        limit=data.get("limit")
                    )
                    return data

                elif response.status_code == 401:
                    logger.error(
                        "Billing service authentication failed",
                        usage_type=usage_type,
                        status_code=401
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication failed with billing service"
                    )

                elif response.status_code == 404:
                    logger.error(
                        "Invalid usage type or billing service endpoint not found",
                        usage_type=usage_type,
                        status_code=404
                    )
                    # Fail-open: allow operation if endpoint doesn't exist
                    return {
                        "allowed": True,
                        "reason": "billing_service_endpoint_not_found"
                    }

                else:
                    logger.warning(
                        f"Billing service returned non-2xx status",
                        usage_type=usage_type,
                        status_code=response.status_code,
                        response_text=response.text[:200]  # Log first 200 chars
                    )
                    # Fail-open: allow operation if billing service has issues
                    return {
                        "allowed": True,
                        "reason": "billing_service_error"
                    }

        except httpx.TimeoutException:
            logger.warning(
                "Billing service timeout - allowing operation (fail-open)",
                usage_type=usage_type,
                timeout_seconds=5.0
            )
            # Fail-open on timeout
            return {
                "allowed": True,
                "reason": "billing_service_timeout"
            }

        except httpx.ConnectError as e:
            logger.error(
                "Cannot connect to billing service - allowing operation (fail-open)",
                usage_type=usage_type,
                error=str(e),
                billing_url=self.billing_url
            )
            # Fail-open on connection error
            return {
                "allowed": True,
                "reason": "billing_service_unavailable"
            }

        except httpx.RequestError as e:
            logger.error(
                f"Billing service request error - allowing operation (fail-open)",
                usage_type=usage_type,
                error=str(e),
                error_type=type(e).__name__
            )
            # Fail-open on any other request error
            return {
                "allowed": True,
                "reason": "billing_service_request_error"
            }

        except Exception as e:
            logger.error(
                f"Unexpected error calling billing service - allowing operation (fail-open)",
                usage_type=usage_type,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            # Fail-open on unexpected errors
            return {
                "allowed": True,
                "reason": "billing_service_unexpected_error"
            }
