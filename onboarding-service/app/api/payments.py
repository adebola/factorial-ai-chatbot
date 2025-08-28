from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import json

from ..core.database import get_db
from ..services.dependencies import get_current_tenant
from ..services.subscription_service import SubscriptionService
from ..services.paystack_service import PaystackService
from ..models.tenant import Tenant
from ..models.subscription import BillingCycle, Payment, PaymentStatus

router = APIRouter()


# Pydantic models for request/response
class SubscriptionCreateRequest(BaseModel):
    plan_id: str = Field(..., description="ID of the plan to subscribe to")
    billing_cycle: BillingCycle = Field(default=BillingCycle.MONTHLY, description="Billing cycle")
    start_trial: bool = Field(default=False, description="Start with trial period")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional metadata")


class PaymentInitializeRequest(BaseModel):
    subscription_id: str = Field(..., description="ID of the subscription to pay for")
    callback_url: Optional[str] = Field(None, description="Custom callback URL")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional payment metadata")


class PaymentVerificationRequest(BaseModel):
    reference: str = Field(..., description="Paystack transaction reference")


class PlanSwitchRequest(BaseModel):
    new_plan_id: str = Field(..., description="ID of the new plan")
    billing_cycle: Optional[BillingCycle] = Field(None, description="New billing cycle")
    prorate: bool = Field(default=True, description="Apply prorated billing")


class SubscriptionCancelRequest(BaseModel):
    cancel_at_period_end: bool = Field(default=True, description="Cancel at end of billing period")
    reason: Optional[str] = Field(None, description="Cancellation reason")


@router.post("/subscriptions/", response_model=Dict[str, Any])
async def create_subscription(
    subscription_data: SubscriptionCreateRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create a new subscription for the current tenant"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Check if tenant already has an active subscription
        existing_subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
        if existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant already has an active subscription"
            )
        
        # Create subscription
        subscription = subscription_service.create_subscription(
            tenant_id=current_tenant.id,
            plan_id=subscription_data.plan_id,
            billing_cycle=subscription_data.billing_cycle,
            start_trial=subscription_data.start_trial,
            metadata=subscription_data.metadata
        )
        
        return {
            "success": True,
            "message": "Subscription created successfully",
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value,
                "amount": str(subscription.amount),
                "currency": subscription.currency,
                "starts_at": subscription.starts_at.isoformat(),
                "ends_at": subscription.ends_at.isoformat(),
                "trial_starts_at": subscription.trial_starts_at.isoformat() if subscription.trial_starts_at else None,
                "trial_ends_at": subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
                "auto_renew": subscription.auto_renew,
                "created_at": subscription.created_at.isoformat()
            }
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.post("/payments/initialize", response_model=Dict[str, Any])
async def initialize_payment(
    payment_data: PaymentInitializeRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
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
        
        if subscription.tenant_id != current_tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only initialize payments for your own subscriptions"
            )
        
        # Initialize payment
        result = await subscription_service.initialize_subscription_payment(
            subscription_id=payment_data.subscription_id,
            tenant_email=current_tenant.email,
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
    current_tenant: Tenant = Depends(get_current_tenant),
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


@router.get("/subscriptions/current", response_model=Dict[str, Any])
async def get_current_subscription(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get the current tenant's active subscription"""
    
    try:
        subscription_service = SubscriptionService(db)
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
        
        if not subscription:
            return {
                "subscription": None,
                "has_subscription": False,
                "message": "No active subscription found"
            }
        
        # Get payment history
        payments = db.query(Payment).filter(
            Payment.subscription_id == subscription.id
        ).order_by(Payment.created_at.desc()).limit(5).all()
        
        return {
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value,
                "amount": str(subscription.amount),
                "currency": subscription.currency,
                "starts_at": subscription.starts_at.isoformat(),
                "ends_at": subscription.ends_at.isoformat(),
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "trial_starts_at": subscription.trial_starts_at.isoformat() if subscription.trial_starts_at else None,
                "trial_ends_at": subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
                "cancelled_at": subscription.cancelled_at.isoformat() if subscription.cancelled_at else None,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "auto_renew": subscription.auto_renew,
                "created_at": subscription.created_at.isoformat()
            },
            "recent_payments": [
                {
                    "id": payment.id,
                    "amount": str(payment.amount),
                    "status": payment.status.value,
                    "transaction_type": payment.transaction_type.value,
                    "created_at": payment.created_at.isoformat(),
                    "processed_at": payment.processed_at.isoformat() if payment.processed_at else None
                }
                for payment in payments
            ],
            "has_subscription": True
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve subscription: {str(e)}"
        )


@router.post("/subscriptions/switch-plan", response_model=Dict[str, Any])
async def switch_subscription_plan(
    switch_data: PlanSwitchRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Switch the current subscription to a different plan"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Switch plan
        result = subscription_service.switch_subscription_plan(
            subscription_id=subscription.id,
            new_plan_id=switch_data.new_plan_id,
            billing_cycle=switch_data.billing_cycle,
            prorate=switch_data.prorate
        )
        
        return {
            "success": True,
            "message": "Plan switched successfully",
            "plan_switch": result
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch plan: {str(e)}"
        )


@router.post("/subscriptions/cancel", response_model=Dict[str, Any])
async def cancel_subscription(
    cancel_data: SubscriptionCancelRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Cancel the current subscription"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Cancel subscription
        result = subscription_service.cancel_subscription(
            subscription_id=subscription.id,
            cancel_at_period_end=cancel_data.cancel_at_period_end,
            reason=cancel_data.reason
        )
        
        return {
            "success": True,
            "message": "Subscription cancelled successfully",
            "cancellation": result
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.get("/subscriptions/history", response_model=Dict[str, Any])
async def get_subscription_history(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription history for the current tenant"""
    
    try:
        subscription_service = SubscriptionService(db)
        subscriptions = subscription_service.get_tenant_subscription_history(current_tenant.id)
        
        return {
            "subscriptions": [
                {
                    "id": sub.id,
                    "plan_id": sub.plan_id,
                    "status": sub.status.value,
                    "billing_cycle": sub.billing_cycle.value,
                    "amount": str(sub.amount),
                    "currency": sub.currency,
                    "starts_at": sub.starts_at.isoformat(),
                    "ends_at": sub.ends_at.isoformat(),
                    "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
                    "cancellation_reason": sub.cancellation_reason,
                    "created_at": sub.created_at.isoformat()
                }
                for sub in subscriptions
            ],
            "total_subscriptions": len(subscriptions)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve subscription history: {str(e)}"
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