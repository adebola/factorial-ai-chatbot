from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import json

from ..core.database import get_db
from ..services.dependencies import validate_token, get_full_tenant_details, TokenClaims
from ..services.subscription_service import SubscriptionService
from ..services.paystack_service import PaystackService
from ..models.subscription import Payment, PaymentStatus, PaymentMethodRecord

router = APIRouter()


# Pydantic models for request/response
class PaymentInitializeRequest(BaseModel):
    subscription_id: str = Field(..., description="ID of the subscription to pay for")
    callback_url: Optional[str] = Field(None, description="Custom callback URL")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional payment metadata")


class PaymentVerificationRequest(BaseModel):
    reference: str = Field(..., description="Paystack transaction reference")




@router.post("/payments/initialize", response_model=Dict[str, Any])
async def initialize_payment(
    payment_data: PaymentInitializeRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Initialize a payment for a subscription"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Verify subscription belongs to tenant
        subscription = subscription_service.get_subscription_by_id(payment_data.subscription_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )
        
        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only initialize payments for your own subscriptions"
            )
        
        # Initialize payment
        result = await subscription_service.initialize_subscription_payment(
            subscription_id=payment_data.subscription_id,
            tenant_email=claims.email,
            metadata=payment_data.metadata
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": "Payment initialized successfully",
                "payment": {
                    "payment_id": result["payment_id"],
                    "reference": result["reference"],
                    "access_code": result["access_code"],
                    "authorization_url": result["authorization_url"],
                    "amount": result["amount"],
                    "currency": subscription.currency
                },
                "paystack_public_key": "pk_test_xxxx"  # You'll need to expose this safely
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize payment: {str(e)}"
        )


@router.post("/payments/verify", response_model=Dict[str, Any])
async def verify_payment(
    verification_data: PaymentVerificationRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Verify a payment transaction"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Verify payment
        result = await subscription_service.verify_subscription_payment(
            reference=verification_data.reference
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": "Payment verified successfully",
                "payment": {
                    "payment_id": result["payment_id"],
                    "subscription_id": result["subscription_id"],
                    "amount": result["amount"],
                    "transaction_id": result["transaction_id"]
                }
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify payment: {str(e)}"
        )



@router.post("/webhooks/paystack", response_model=Dict[str, Any])
async def handle_paystack_webhook(
    request: Request,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Handle Paystack webhook events"""
    
    try:
        # Get raw body and signature
        body = await request.body()
        signature = request.headers.get("x-paystack-signature", "")
        
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Paystack signature"
            )
        
        # Initialize services
        paystack_service = PaystackService(db)
        subscription_service = SubscriptionService(db)
        
        # Verify webhook signature
        if not paystack_service.verify_webhook_signature(body, signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature"
            )
        
        # Parse webhook data
        try:
            webhook_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        event_type = webhook_data.get("event")
        event_id = webhook_data.get("id")
        data = webhook_data.get("data", {})
        
        # Log webhook event
        webhook = paystack_service.log_webhook_event(
            event_type=event_type,
            event_id=event_id,
            raw_data=webhook_data,
            signature=signature
        )
        
        # Process webhook based on event type
        try:
            if event_type == "charge.success":
                reference = data.get("reference")
                if reference:
                    # Verify and process payment
                    await subscription_service.verify_subscription_payment(reference)
            
            elif event_type == "charge.failed":
                reference = data.get("reference")
                if reference:
                    # Mark payment as failed
                    payment = db.query(Payment).filter(
                        Payment.paystack_reference == reference
                    ).first()
                    if payment:
                        payment.status = PaymentStatus.FAILED
                        payment.failure_reason = data.get("gateway_response", "Payment failed")
                        db.commit()
            
            # Mark webhook as processed
            paystack_service.mark_webhook_processed(webhook.id, success=True)
            
        except Exception as processing_error:
            # Mark webhook as failed
            paystack_service.mark_webhook_processed(
                webhook.id, 
                success=False, 
                error=str(processing_error)
            )
            raise
        
        return {
            "success": True,
            "message": "Webhook processed successfully",
            "event_type": event_type,
            "event_id": event_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook: {str(e)}"
        )


@router.get("/payment-methods", response_model=Dict[str, Any])
async def get_payment_methods(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get saved payment methods for the tenant"""
    
    try:
        payment_methods = db.query(PaymentMethodRecord).filter(
            PaymentMethodRecord.tenant_id == claims.tenant_id,
            PaymentMethodRecord.is_active == True
        ).order_by(PaymentMethodRecord.created_at.desc()).all()
        
        return {
            "payment_methods": [
                {
                    "id": pm.id,
                    "type": pm.type.value,
                    "is_default": pm.is_default,
                    "card_last_four": pm.card_last_four,
                    "card_brand": pm.card_brand,
                    "card_exp_month": pm.card_exp_month,
                    "card_exp_year": pm.card_exp_year,
                    "bank_name": pm.bank_name,
                    "created_at": pm.created_at.isoformat()
                }
                for pm in payment_methods
            ],
            "total_methods": len(payment_methods)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve payment methods: {str(e)}"
        )


@router.delete("/payment-methods/{method_id}", response_model=Dict[str, Any])
async def delete_payment_method(
    method_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a saved payment method"""
    
    try:
        payment_method = db.query(PaymentMethodRecord).filter(
            PaymentMethodRecord.id == method_id,
            PaymentMethodRecord.tenant_id == claims.tenant_id
        ).first()
        
        if not payment_method:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment method not found"
            )
        
        payment_method.is_active = False
        payment_method.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": "Payment method deleted successfully",
            "method_id": method_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete payment method: {str(e)}"
        )