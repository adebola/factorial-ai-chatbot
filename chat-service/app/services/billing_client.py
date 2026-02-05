"""
HTTP client for billing-service API.

This client is used by the chat-service to check subscription status
and usage limits before processing chat messages.
"""
import logging
import os
from typing import Optional, Tuple
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class BillingServiceClient:
    """Client for communicating with the billing-service"""

    def __init__(self):
        """Initialize billing service client"""
        self.base_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
        self.api_prefix = "/api/v1/restrictions"
        self.timeout = 5.0  # 5 second timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def check_can_send_chat(self, tenant_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant can send a chat message.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        url = f"{self.base_url}{self.api_prefix}/check/can-send-chat/{tenant_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    return data.get("allowed", False), data.get("reason")
                elif response.status_code == 404:
                    logger.warning(f"No subscription found for tenant {tenant_id}")
                    return False, "No active subscription found"
                else:
                    logger.error(
                        f"Billing service returned error: {response.status_code}",
                        extra={"tenant_id": tenant_id, "status": response.status_code}
                    )
                    # On error, fail open (allow chat) to prevent service disruption
                    return True, None

        except httpx.TimeoutException:
            logger.error(
                f"Timeout calling billing service for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "url": url}
            )
            # Fail open on timeout
            return True, None

        except httpx.HTTPError as e:
            logger.error(
                f"HTTP error calling billing service: {e}",
                extra={"tenant_id": tenant_id, "error": str(e)})
            # Fail open on HTTP error
            return True, None

        except Exception as e:
            logger.error(
                f"Unexpected error calling billing service: {e}",
                extra={"tenant_id": tenant_id, "error": str(e)})
            # Fail open on unexpected error
            return True, None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def get_usage_summary(self, tenant_id: str) -> Optional[dict]:
        """
        Get usage summary for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Usage summary dictionary or None on error
        """
        url = f"{self.base_url}{self.api_prefix}/usage/{tenant_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"No subscription found for tenant {tenant_id}")
                    return None
                else:
                    logger.error(
                        f"Billing service returned error: {response.status_code}",
                        extra={"tenant_id": tenant_id, "status": response.status_code}
                    )
                    return None

        except httpx.TimeoutException:
            logger.error(
                f"Timeout calling billing service for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "url": url}
            )
            return None

        except Exception as e:
            logger.error(
                f"Error getting usage summary: {e}",
                extra={"tenant_id": tenant_id, "error": str(e)})
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def check_subscription_status(
        self,
        tenant_id: str,
        include_grace_period: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if tenant has an active subscription.

        Args:
            tenant_id: Tenant ID
            include_grace_period: Whether to include grace period

        Returns:
            Tuple of (is_active, reason_if_not_active)
        """
        url = f"{self.base_url}{self.api_prefix}/check/subscription/{tenant_id}"
        params = {"include_grace_period": include_grace_period}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return data.get("is_active", False), data.get("reason")
                else:
                    logger.error(
                        f"Billing service returned error: {response.status_code}",
                        extra={"tenant_id": tenant_id, "status": response.status_code}
                    )
                    # Fail open
                    return True, None

        except httpx.TimeoutException:
            logger.error(
                f"Timeout calling billing service for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "url": url}
            )
            return True, None

        except Exception as e:
            logger.error(
                f"Error checking subscription status: {e}",
                extra={"tenant_id": tenant_id, "error": str(e)})
            return True, None


# Global instance
billing_client = BillingServiceClient()
