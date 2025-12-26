import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.subscription import PaystackWebhook


class PaystackService:
    """Paystack payment gateway integration service"""

    def __init__(self, db: Session):
        import os
        self.db = db
        self.base_url = "https://api.paystack.co"
        self.secret_key = os.environ.get("PAYSTACK_SECRET_KEY")
        self.public_key = os.environ.get("PAYSTACK_PUBLIC_KEY")

        if not self.secret_key:
            raise ValueError("PAYSTACK_SECRET_KEY is required")

        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

    async def initialize_transaction(
        self,
        email: str,
        amount: Decimal,
        currency: str = "NGN",
        reference: Optional[str] = None,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Initialize a new payment transaction with Paystack"""

        # Generate reference if not provided
        if not reference:
            reference = f"factorialbot_{uuid.uuid4().hex[:16]}"

        # Convert amount to kobo (Paystack requires the smallest currency unit)
        amount_in_kobo = int(amount * 100)

        payload = {
            "email": email,
            "amount": amount_in_kobo,
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url or os.environ.get("PAYMENT_CALLBACK_URL"),
            "metadata": metadata or {},
            "channels": channels or ["card", "bank", "ussd", "qr", "mobile_money"]
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"],
                            "reference": reference,
                            "access_code": data["data"]["access_code"],
                            "authorization_url": data["data"]["authorization_url"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Transaction initialization failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Request failed: {str(e)}"
                }

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """Verify a transaction with Paystack"""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        transaction_data = data["data"]
                        return {
                            "success": True,
                            "data": transaction_data,
                            "verified": transaction_data.get("status") == "success",
                            "amount": Decimal(str(transaction_data.get("amount", 0))) / 100,  # Convert from kobo
                            "currency": transaction_data.get("currency"),
                            "reference": transaction_data.get("reference"),
                            "transaction_id": transaction_data.get("id"),
                            "paid_at": transaction_data.get("paid_at"),
                            "channel": transaction_data.get("channel"),
                            "customer": transaction_data.get("customer", {}),
                            "authorization": transaction_data.get("authorization", {}),
                            "metadata": transaction_data.get("metadata", {})
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Transaction verification failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Verification request failed: {str(e)}"
                }

    async def charge_authorization(
        self,
        authorization_code: str,
        email: str,
        amount: Decimal,
        currency: str = "NGN",
        reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Charge a previously authorized payment method"""

        if not reference:
            reference = f"factorialbot_{uuid.uuid4().hex[:16]}"

        # Convert amount to kobo
        amount_in_kobo = int(amount * 100)

        payload = {
            "authorization_code": authorization_code,
            "email": email,
            "amount": amount_in_kobo,
            "currency": currency,
            "reference": reference,
            "metadata": metadata or {}
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/transaction/charge_authorization",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"],
                            "reference": reference
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Authorization charge failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Charge request failed: {str(e)}"
                }

    async def create_customer(
        self,
        email: str,
        first_name: str,
        last_name: str,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a customer on Paystack"""

        payload = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "metadata": metadata or {}
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/customer",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"],
                            "customer_code": data["data"]["customer_code"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Customer creation failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Customer creation request failed: {str(e)}"
                }

    async def get_customer(self, customer_code: str) -> Dict[str, Any]:
        """Get customer details from Paystack"""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/customer/{customer_code}",
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Customer retrieval failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Customer retrieval request failed: {str(e)}"
                }

    async def create_refund(
        self,
        transaction_reference: str,
        amount: Optional[Decimal] = None,
        currency: str = "NGN",
        customer_note: Optional[str] = None,
        merchant_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a refund for a transaction"""

        payload = {
            "transaction": transaction_reference,
            "currency": currency
        }

        if amount:
            # Convert to kobo
            payload["amount"] = int(amount * 100)

        if customer_note:
            payload["customer_note"] = customer_note

        if merchant_note:
            payload["merchant_note"] = merchant_note

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/refund",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"],
                            "refund_id": data["data"]["id"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Refund creation failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Refund request failed: {str(e)}"
                }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Paystack webhook signature.

        Paystack signs webhook payloads using HMAC SHA512 with your SECRET KEY.
        The signature is sent in the 'x-paystack-signature' header.

        Reference: https://paystack.com/docs/payments/webhooks/
        """
        if not self.secret_key:
            raise ValueError("PAYSTACK_SECRET_KEY is required for webhook verification")

        try:
            # Generate expected signature using HMAC SHA512 with secret key
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            # Compare signatures (constant-time comparison to prevent timing attacks)
            return hmac.compare_digest(expected_signature, signature)
        except Exception:
            return False

    def log_webhook_event(
        self,
        event_type: str,
        event_id: str,
        raw_data: Dict[str, Any],
        signature: str
    ) -> PaystackWebhook:
        """Log a webhook event to the database"""

        webhook = PaystackWebhook(
            event_type=event_type,
            paystack_event_id=event_id,
            raw_data=raw_data,
            signature=signature
        )

        self.db.add(webhook)
        self.db.commit()
        self.db.refresh(webhook)

        return webhook

    def mark_webhook_processed(
        self,
        webhook_id: str,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """Mark a webhook as processed"""

        webhook = self.db.query(PaystackWebhook).filter(
            PaystackWebhook.id == webhook_id
        ).first()

        if webhook:
            webhook.processed = success
            webhook.processing_attempts += 1
            webhook.processed_at = datetime.now(timezone.utc)

            if error:
                webhook.last_processing_error = error

            self.db.commit()

    async def get_transaction_timeline(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction timeline from Paystack"""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/transaction/timeline/{transaction_id}",
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status"):
                        return {
                            "success": True,
                            "data": data["data"]
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("message", "Timeline retrieval failed")
                        }
                else:
                    error_data = response.json() if response.content else {}
                    return {
                        "success": False,
                        "error": error_data.get("message", f"HTTP {response.status_code}")
                    }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Timeline request failed: {str(e)}"
                }

    def calculate_amount_in_kobo(self, amount: Decimal) -> int:
        """Convert amount to kobo (smallest currency unit)"""
        return int(amount * 100)

    def calculate_amount_from_kobo(self, amount_in_kobo: int) -> Decimal:
        """Convert amount from kobo to decimal"""
        return Decimal(str(amount_in_kobo)) / 100
