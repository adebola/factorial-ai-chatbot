"""
Paystack API Client

This module provides integration with Paystack payment gateway for:
- Payment initialization
- Payment verification
- Transaction management
- Webhook signature validation

Documentation: https://paystack.com/docs/api/
"""
import os
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    """Base exception for Paystack API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class PaystackClient:
    """
    Client for interacting with Paystack API.

    Handles payment initialization, verification, and webhook validation.
    """

    def __init__(self):
        """Initialize the Paystack client with credentials from the environment"""
        self.secret_key = os.environ.get("PAYSTACK_SECRET_KEY")
        self.public_key = os.environ.get("PAYSTACK_PUBLIC_KEY")
        self.webhook_secret = os.environ.get("PAYSTACK_WEBHOOK_SECRET")
        self.callback_url = os.environ.get("PAYMENT_CALLBACK_URL", "http://localhost:8080/api/v1/payments/callback")

        # Paystack API base URL
        self.base_url = "https://api.paystack.co"

        # Validate required credentials
        if not self.secret_key:
            logger.warning("PAYSTACK_SECRET_KEY not set - payment processing will fail")
        if not self.webhook_secret:
            logger.warning("PAYSTACK_WEBHOOK_SECRET not set - webhook validation will fail")

        logger.info(f"Paystack client initialized with callback URL: {self.callback_url}")

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Paystack API requests"""
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def initialize_transaction(
        self,
        email: str,
        amount: Decimal,
        reference: str,
        metadata: Optional[Dict[str, Any]] = None,
        currency: str = "NGN"
    ) -> Dict[str, Any]:
        """
        Initialize a payment transaction with Paystack.

        Args:
            email: Customer's email address
            amount: Amount in smallest currency unit (kobo for NGN, cents for USD)
            reference: Unique transaction reference (should be subscription_id or similar)
            metadata: Additional transaction metadata (tenant_id, plan_id, etc.)
            currency: Currency code (NGN, USD, GHS, ZAR, etc.)

        Returns:
            Dict containing:
                - authorization_url: URL to redirect user for payment
                - access_code: Paystack access code
                - reference: Transaction reference

        Raises:
            PaystackError: If initialization fails

        Example:
            >>> client = PaystackClient()
            >>> result = await client.initialize_transaction(
            ...     email="user@example.com",
            ...     amount=Decimal("999.00"),  # Will be converted to 99900 kobo
            ...     reference="sub_abc123",
            ...     metadata={"tenant_id": "tenant_123", "plan_id": "plan_pro"}
            ... )
            >>> print(result["authorization_url"])
            https://checkout.paystack.com/abc123xyz
        """
        # Convert amount to smallest currency unit (kobo/cents)
        amount_in_kobo = int(amount * 100)

        payload = {
            "email": email,
            "amount": amount_in_kobo,
            "reference": reference,
            "callback_url": self.callback_url,
            "currency": currency,
            "metadata": metadata or {}
        }

        logger.info(
            f"Initializing Paystack transaction",
            extra={
                "reference": reference,
                "email": email,
                "amount": str(amount),
                "currency": currency
            }
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    json=payload,
                    headers=self._get_headers()
                )

                data = response.json()

                if response.status_code == 200 and data.get("status"):
                    logger.info(
                        f"Transaction initialized successfully",
                        extra={
                            "reference": reference,
                            "authorization_url": data["data"]["authorization_url"]
                        }
                    )
                    return data["data"]
                else:
                    error_message = data.get("message", "Unknown error")
                    logger.error(
                        f"Paystack initialization failed: {error_message}",
                        extra={"reference": reference, "response": data}
                    )
                    raise PaystackError(
                        message=error_message,
                        status_code=response.status_code,
                        response_data=data
                    )

        except httpx.HTTPError as e:
            logger.error(
                f"HTTP error initializing transaction: {e}",
                extra={"reference": reference},
                exc_info=True
            )
            raise PaystackError(f"Failed to connect to Paystack: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error initializing transaction: {e}",
                extra={"reference": reference},
                exc_info=True
            )
            raise PaystackError(f"Payment initialization failed: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """
        Verify a payment transaction with Paystack.

        Should be called after user completes payment to confirm success.

        Args:
            reference: Transaction reference to verify

        Returns:
            Dict containing transaction details:
                - status: Transaction status (success, failed, abandoned, etc.)
                - amount: Amount paid (in kobo/cents)
                - currency: Currency code
                - paid_at: Payment timestamp
                - channel: Payment channel (card, bank, etc.)
                - metadata: Custom metadata passed during initialization

        Raises:
            PaystackError: If verification fails

        Example:
            >>> result = await client.verify_transaction("sub_abc123")
            >>> if result["status"] == "success":
            ...     print(f"Payment successful: {result['amount'] / 100} {result['currency']}")
        """
        logger.info(f"Verifying transaction", extra={"reference": reference})

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self._get_headers()
                )

                data = response.json()

                if response.status_code == 200 and data.get("status"):
                    transaction_data = data["data"]
                    logger.info(
                        f"Transaction verified",
                        extra={
                            "reference": reference,
                            "status": transaction_data.get("status"),
                            "amount": transaction_data.get("amount")
                        }
                    )
                    return transaction_data
                else:
                    error_message = data.get("message", "Verification failed")
                    logger.error(
                        f"Transaction verification failed: {error_message}",
                        extra={"reference": reference, "response": data}
                    )
                    raise PaystackError(
                        message=error_message,
                        status_code=response.status_code,
                        response_data=data
                    )

        except httpx.HTTPError as e:
            logger.error(
                f"HTTP error verifying transaction: {e}",
                extra={"reference": reference},
                exc_info=True
            )
            raise PaystackError(f"Failed to connect to Paystack: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error verifying transaction: {e}",
                extra={"reference": reference},
                exc_info=True
            )
            raise PaystackError(f"Payment verification failed: {str(e)}")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify that a webhook request is from Paystack.

        Paystack signs webhook payloads with HMAC SHA512 using your webhook secret.
        This method validates the signature to prevent spoofed webhooks.

        Args:
            payload: Raw request body (bytes)
            signature: X-Paystack-Signature header value

        Returns:
            True if signature is valid, False otherwise

        Example:
            >>> @app.post("/webhooks/paystack")
            >>> async def paystack_webhook(request: Request):
            ...     payload = await request.body()
            ...     signature = request.headers.get("X-Paystack-Signature")
            ...
            ...     if not paystack_client.verify_webhook_signature(payload, signature):
            ...         raise HTTPException(401, "Invalid signature")
            ...
            ...     # Process webhook...
        """
        if not self.webhook_secret:
            logger.error("Webhook secret not configured - cannot verify signature")
            return False

        if not signature:
            logger.warning("No signature provided in webhook request")
            return False

        # Compute HMAC SHA512 of payload
        computed_signature = hmac.new(
            key=self.webhook_secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        # Compare signatures securely (prevents timing attacks)
        is_valid = hmac.compare_digest(computed_signature, signature)

        if not is_valid:
            logger.warning(
                "Webhook signature verification failed",
                extra={
                    "provided_signature": signature[:20] + "...",
                    "computed_signature": computed_signature[:20] + "..."
                }
            )

        return is_valid

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def refund_transaction(
        self,
        transaction_reference: str,
        amount: Optional[Decimal] = None,
        currency: str = "NGN",
        customer_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate a refund for a transaction.

        Args:
            transaction_reference: Original transaction reference to refund
            amount: Amount to refund (if partial). If None, full refund.
            currency: Currency code
            customer_note: Optional note for customer

        Returns:
            Dict containing refund details

        Raises:
            PaystackError: If refund fails
        """
        payload = {
            "transaction": transaction_reference,
            "currency": currency
        }

        if amount:
            # Convert to kobo/cents
            payload["amount"] = int(amount * 100)

        if customer_note:
            payload["customer_note"] = customer_note

        logger.info(
            f"Initiating refund",
            extra={
                "reference": transaction_reference,
                "amount": str(amount) if amount else "full"
            }
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/refund",
                    json=payload,
                    headers=self._get_headers()
                )

                data = response.json()

                if response.status_code in [200, 201] and data.get("status"):
                    logger.info(
                        f"Refund initiated successfully",
                        extra={"reference": transaction_reference}
                    )
                    return data["data"]
                else:
                    error_message = data.get("message", "Refund failed")
                    logger.error(
                        f"Refund failed: {error_message}",
                        extra={"reference": transaction_reference, "response": data}
                    )
                    raise PaystackError(
                        message=error_message,
                        status_code=response.status_code,
                        response_data=data
                    )

        except httpx.HTTPError as e:
            logger.error(
                f"HTTP error initiating refund: {e}",
                extra={"reference": transaction_reference},
                exc_info=True
            )
            raise PaystackError(f"Failed to connect to Paystack: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error initiating refund: {e}",
                extra={"reference": transaction_reference},
                exc_info=True
            )
            raise PaystackError(f"Refund failed: {str(e)}")


# Global instance
paystack_client = PaystackClient()
