from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..core.database import get_db
from ..models.subscription import (
    Subscription, SubscriptionStatus, BillingCycle, UsageTracking,
    SubscriptionChange, Payment, PaymentStatus
)
from ..services.dependencies import TokenClaims, validate_token
from ..services.plan_service import PlanService
from ..services.subscription_service import SubscriptionService
from ..services.rabbitmq_service import rabbitmq_service
from ..middleware.feature_flags import get_tenant_features

router = APIRouter()


# Pydantic models for request/response
class UsageStatsResponse(BaseModel):
    documents_used: int
    documents_limit: int
    websites_used: int
    websites_limit: int
    daily_chats_used: int
    daily_chats_limit: int
    monthly_chats_used: int
    monthly_chats_limit: int
    usage_percentage: Dict[str, float]
    period_start: str
    period_end: str


class SubscriptionAnalyticsResponse(BaseModel):
    total_subscriptions: int
    active_subscriptions: int
    trial_subscriptions: int
    cancelled_subscriptions: int
    monthly_revenue: float
    yearly_revenue: float
    churn_rate: float
    growth_rate: float


# Additional models for subscription management
class SubscriptionCreateRequest(BaseModel):
    plan_id: str = Field(..., description="ID of the plan to subscribe to")
    billing_cycle: BillingCycle = Field(default=BillingCycle.MONTHLY, description="Billing cycle")
    start_trial: bool = Field(default=False, description="Start with trial period")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional metadata")


class PlanSwitchRequest(BaseModel):
    new_plan_id: str = Field(..., description="ID of the new plan")
    billing_cycle: Optional[BillingCycle] = Field(None, description="New billing cycle")
    prorate: bool = Field(default=True, description="Apply prorated billing")


class SubscriptionCancelRequest(BaseModel):
    cancel_at_period_end: bool = Field(default=True, description="Cancel at end of billing period")
    reason: Optional[str] = Field(None, description="Cancellation reason")


@router.get("/usage/current", response_model=Dict[str, Any])
async def get_current_usage(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get current usage statistics for the tenant"""

    try:
        # Get current time at the beginning to avoid scope issues
        # Use timezone-aware datetime to match database timestamps
        now = datetime.now(timezone.utc)

        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)

        # Get the current subscription (fallback to the Free plan if none exists)
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)

        if subscription:
            # Get plan limits from subscription
            plan = plan_service.get_plan_by_id(subscription.plan_id)
            if not plan:
                # Fallback to Free plan if subscription plan not found
                plan = plan_service.get_plan_by_name("Free")
        else:
            # No subscription - use Free plan limits
            plan = plan_service.get_plan_by_name("Free")

        if not plan:
            # Create default plan limits if the Free plan doesn't exist
            class DefaultPlan:
                document_limit = 5
                website_limit = 1
                daily_chat_limit = 10
                monthly_chat_limit = 300
                name = "Free"
                id = "default"
            plan = DefaultPlan()

        # Get usage tracking record from local database
        # This data is built from async messages received from other services
        usage = None
        if subscription:
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

            if not usage:
                # Initialize usage tracking if not exists
                subscription_service._initialize_usage_tracking(subscription)
                usage = db.query(UsageTracking).filter(
                    UsageTracking.subscription_id == subscription.id
                ).first()

            # Check and reset usage periods if needed (daily/monthly resets)
            if usage:
                usage = subscription_service.check_and_reset_usage_periods(usage)

        # If no subscription exists, create a default usage object for display
        if not usage:
            class DefaultUsage:
                documents_used = 0
                websites_used = 0
                daily_chats_used = 0
                monthly_chats_used = 0
                api_calls_made = 0
                daily_reset_at = None
                monthly_reset_at = None
                period_start = now
                period_end = now + timedelta(days=30)
            usage = DefaultUsage()

        # Helper function to calculate percentage for non-unlimited limits
        def calc_percentage(used: int, limit: int) -> float:
            if limit == -1:  # Unlimited
                return 0.0
            if limit <= 0:
                return 0.0
            return (used / limit * 100)

        # Helper function to calculate remaining for non-unlimited limits
        def calc_remaining(used: int, limit: int) -> int:
            if limit == -1:  # Unlimited
                return -1
            return max(0, limit - used)

        # Calculate usage percentages and remaining values
        doc_percentage = calc_percentage(usage.documents_used, plan.document_limit)
        website_percentage = calc_percentage(usage.websites_used, plan.website_limit)
        daily_chat_percentage = calc_percentage(usage.daily_chats_used, plan.daily_chat_limit)
        monthly_chat_percentage = calc_percentage(usage.monthly_chats_used, plan.monthly_chat_limit)

        return {
            "usage_statistics": {
                "documents": {
                    "used": usage.documents_used,
                    "limit": plan.document_limit,
                    "unlimited": plan.document_limit == -1,
                    "percentage": round(doc_percentage, 2),
                    "remaining": calc_remaining(usage.documents_used, plan.document_limit)
                },
                "websites": {
                    "used": usage.websites_used,
                    "limit": plan.website_limit,
                    "unlimited": plan.website_limit == -1,
                    "percentage": round(website_percentage, 2),
                    "remaining": calc_remaining(usage.websites_used, plan.website_limit)
                },
                "daily_chats": {
                    "used": usage.daily_chats_used,
                    "limit": plan.daily_chat_limit,
                    "unlimited": plan.daily_chat_limit == -1,
                    "percentage": round(daily_chat_percentage, 2),
                    "remaining": calc_remaining(usage.daily_chats_used, plan.daily_chat_limit),
                    "resets_at": usage.daily_reset_at.isoformat() if usage.daily_reset_at else None
                },
                "monthly_chats": {
                    "used": usage.monthly_chats_used,
                    "limit": plan.monthly_chat_limit,
                    "unlimited": plan.monthly_chat_limit == -1,
                    "percentage": round(monthly_chat_percentage, 2),
                    "remaining": calc_remaining(usage.monthly_chats_used, plan.monthly_chat_limit),
                    "resets_at": usage.monthly_reset_at.isoformat() if usage.monthly_reset_at else None
                },
                "api_calls": {
                    "used": usage.api_calls_made,
                    "limit": -1,
                    "unlimited": True
                }
            },
            "billing_period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat(),
                "days_remaining": (usage.period_end - now).days
            },
            "subscription": {
                "id": subscription.id if subscription else None,
                "plan_id": subscription.plan_id if subscription else plan.id,
                "plan_name": plan.name,
                "status": subscription.status if subscription else "none",
                "billing_cycle": subscription.billing_cycle if subscription else "none"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve usage statistics: {str(e)}"
        )


@router.post("/usage/increment", response_model=Dict[str, Any])
async def increment_usage(
    usage_type: str,
    amount: int = 1,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Increment usage counter for a specific metric"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Get usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()
        
        if not usage:
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()
        
        # Increment the appropriate counter
        if usage_type == "documents":
            usage.documents_used += amount
        elif usage_type == "websites":
            usage.websites_used += amount
        elif usage_type == "daily_chats":
            usage.daily_chats_used += amount
        elif usage_type == "monthly_chats":
            usage.monthly_chats_used += amount
        elif usage_type == "api_calls":
            usage.api_calls_made += amount
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid usage type"
            )
        
        usage.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        return {
            "success": True,
            "message": f"Usage incremented successfully",
            "usage_type": usage_type,
            "amount_added": amount,
            "new_total": getattr(usage, f"{usage_type}_used" if usage_type != "api_calls" else "api_calls_made")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to increment usage: {str(e)}"
        )


@router.get("/usage/check-limit/{usage_type}", response_model=Dict[str, Any])
async def check_usage_limit(
    usage_type: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Check if tenant can perform an action based on usage limits"""
    
    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)
        
        # Get current subscription and plan
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if not subscription:
            return {
                "allowed": False,
                "reason": "No active subscription",
                "usage_type": usage_type
            }
        
        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return {
                "allowed": False,
                "reason": "Plan not found",
                "usage_type": usage_type
            }
        
        # Get usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()
        
        if not usage:
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()
        
        # Check limits based on usage type
        # Note: limit of -1 means unlimited
        if usage_type == "documents":
            current = usage.documents_used
            limit = plan.document_limit
            allowed = (limit == -1) or (usage.documents_used < plan.document_limit)
        elif usage_type == "websites":
            current = usage.websites_used
            limit = plan.website_limit
            allowed = (limit == -1) or (usage.websites_used < plan.website_limit)
        elif usage_type == "daily_chats":
            current = usage.daily_chats_used
            limit = plan.daily_chat_limit
            allowed = (limit == -1) or (usage.daily_chats_used < plan.daily_chat_limit)
        elif usage_type == "monthly_chats":
            current = usage.monthly_chats_used
            limit = plan.monthly_chat_limit
            allowed = (limit == -1) or (usage.monthly_chats_used < plan.monthly_chat_limit)
        elif usage_type == "api_calls":
            current = usage.api_calls_made
            limit = -1  # API calls always unlimited
            allowed = True
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid usage type"
            )

        return {
            "allowed": allowed,
            "usage_type": usage_type,
            "current_usage": current,
            "limit": limit,
            "remaining": max(0, limit - current) if limit > 0 else -1,
            "unlimited": limit == -1,
            "reason": None if allowed else f"{usage_type.replace('_', ' ').title()} limit exceeded"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check usage limit: {str(e)}"
        )


@router.get("/changes/history", response_model=Dict[str, Any])
async def get_subscription_changes(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription change history for the tenant"""

    try:
        changes = db.query(SubscriptionChange).filter(
            SubscriptionChange.tenant_id == claims.tenant_id,
        ).order_by(SubscriptionChange.created_at.desc()).limit(20).all()

        return {
            "changes": [
                {
                    "id": change.id,
                    "change_type": change.change_type,
                    "previous_plan_id": change.previous_plan_id,
                    "new_plan_id": change.new_plan_id,
                    "previous_amount": str(change.previous_amount) if change.previous_amount else None,
                    "new_amount": str(change.new_amount) if change.new_amount else None,
                    "prorated_amount": str(change.prorated_amount) if change.prorated_amount else None,
                    "reason": change.reason,
                    "initiated_by": change.initiated_by,
                    "effective_at": change.effective_at.isoformat(),
                    "created_at": change.created_at.isoformat()
                }
                for change in changes
            ],
            "total_changes": len(changes)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve subscription changes: {str(e)}"
        )


@router.get("/features", response_model=Dict[str, Any])
async def get_plan_features(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get feature flags for the tenant's current plan"""

    try:
        features = await get_tenant_features(claims.tenant_id, db)

        return {
            "tenant_id": claims.tenant_id,
            "features": features
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve plan features: {str(e)}"
        )


@router.post("/create", response_model=Dict[str, Any])
async def create_subscription(
    subscription_data: SubscriptionCreateRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create a new subscription for the current tenant"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Check if tenant already has an active subscription
        existing_subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant already has an active subscription"
            )
        
        # Create subscription
        subscription = subscription_service.create_subscription(
            tenant_id=claims.tenant_id,
            plan_id=subscription_data.plan_id,
            billing_cycle=subscription_data.billing_cycle,
            start_trial=subscription_data.start_trial,
            metadata=subscription_data.metadata
        )
        
        # Send message to auth server to update tenant's plan_id and subscription_id
        try:
            await rabbitmq_service.publish_plan_update(
                tenant_id=claims.tenant_id,
                subscription_id=subscription.id,
                plan_id=subscription_data.plan_id,
                action="subscription_created"
            )
        except Exception as e:
            # Log error but don't fail the subscription creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to publish plan update message: {e}")
        
        return {
            "success": True,
            "message": "Subscription created successfully",
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status,
                "billing_cycle": subscription.billing_cycle,
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


@router.get("/current", response_model=Dict[str, Any])
async def get_current_subscription(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get the current tenant's active subscription.

    Performs real-time status check to ensure expired subscriptions are marked correctly,
    even if the scheduled expiration job hasn't run yet.
    """

    try:
        subscription_service = SubscriptionService(db)
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)

        if not subscription:
            return {
                "subscription": None,
                "has_subscription": False,
                "message": "No active subscription found"
            }

        # Check and update subscription status if needed (real-time expiration check)
        subscription = subscription_service.check_and_update_subscription_status(subscription)
        
        # Get payment history
        payments = db.query(Payment).filter(
            Payment.subscription_id == subscription.id
        ).order_by(Payment.created_at.desc()).limit(5).all()
        
        return {
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status,
                "billing_cycle": subscription.billing_cycle,
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
                    "status": payment.status,
                    "transaction_type": payment.transaction_type,  # Already a string from DB
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


@router.post("/switch-plan", response_model=Dict[str, Any])
async def switch_subscription_plan(
    switch_data: PlanSwitchRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Switch the current subscription to a different plan"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
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
        
        # Send message to auth server to update tenant's plan_id
        try:
            await rabbitmq_service.publish_plan_switch(
                tenant_id=claims.tenant_id,
                old_plan_id=subscription.plan_id,
                new_plan_id=switch_data.new_plan_id
            )
        except Exception as e:
            # Log error but don't fail the plan switch
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to publish plan switch message: {e}")
        
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


@router.post("/cancel", response_model=Dict[str, Any])
async def cancel_subscription(
    cancel_data: SubscriptionCancelRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Cancel the current subscription"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
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


@router.post("/{subscription_id}/renew", response_model=Dict[str, Any])
async def renew_subscription(
    subscription_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Renew subscription before or after expiration.

    **Features**:
    - Can renew ACTIVE subscriptions (extends current billing period)
    - Can renew EXPIRED subscriptions (reactivates with new period)
    - Always charges FULL plan cost (no proration)
    - Returns Paystack payment URL for user to complete payment

    **Validation**:
    - Subscription must belong to authenticated tenant
    - Cannot renew CANCELLED subscriptions
    - Cannot renew PENDING subscriptions (never activated)
    - Cannot renew subscriptions with pending plan changes

    **Returns**:
    - Payment initialization details (payment_url, reference, amount)
    - New billing period dates (new_period_start, new_period_end)
    """
    try:
        subscription_service = SubscriptionService(db)

        # Verify the subscription exists and belongs to the tenant
        subscription = subscription_service.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only renew your own subscriptions"
            )

        # Renew subscription (initializes payment)
        result = await subscription_service.renew_subscription(
            subscription_id=subscription_id,
            user_email=claims.email,
            user_full_name=claims.full_name
        )

        return {
            "success": True,
            "message": "Renewal payment initialized successfully",
            "renewal": result
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
            detail=f"Failed to renew subscription: {str(e)}"
        )


@router.get("/history", response_model=Dict[str, Any])
async def get_subscription_history(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription history for the current tenant"""
    
    try:
        subscription_service = SubscriptionService(db)
        subscriptions = subscription_service.get_tenant_subscription_history(claims.tenant_id)
        
        return {
            "subscriptions": [
                {
                    "id": sub.id,
                    "plan_id": sub.plan_id,
                    "status": sub.status,
                    "billing_cycle": sub.billing_cycle,
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


# Admin endpoints
@router.get("/admin/analytics", response_model=Dict[str, Any])
async def get_subscription_analytics(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription analytics (Admin only)"""
    
    try:
        # Get subscription counts
        total_subs = db.query(Subscription).count()
        active_subs = db.query(Subscription).filter(
            Subscription.status == 'active'
        ).count()
        trial_subs = db.query(Subscription).filter(
            Subscription.status == 'trialing'
        ).count()
        cancelled_subs = db.query(Subscription).filter(
            Subscription.status == 'cancelled'
        ).count()

        # Calculate revenue (simplified)
        monthly_revenue = db.query(Subscription).filter(
            and_(
                Subscription.status.in_(['active', 'trialing']),
                Subscription.billing_cycle == 'monthly'
            )
        ).all()

        yearly_revenue = db.query(Subscription).filter(
            and_(
                Subscription.status.in_(['active', 'trialing']),
                Subscription.billing_cycle == 'yearly'
            )
        ).all()
        
        monthly_rev = sum(float(sub.amount) for sub in monthly_revenue)
        yearly_rev = sum(float(sub.amount) for sub in yearly_revenue)
        
        # Calculate churn rate (simplified - last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        churned_count = db.query(Subscription).filter(
            and_(
                Subscription.status == 'cancelled',
                Subscription.cancelled_at >= thirty_days_ago
            )
        ).count()
        
        churn_rate = (churned_count / max(1, total_subs)) * 100
        
        # Calculate growth rate (new subscriptions in last 30 days)
        new_subs_count = db.query(Subscription).filter(
            Subscription.created_at >= thirty_days_ago
        ).count()
        
        growth_rate = (new_subs_count / max(1, total_subs)) * 100
        
        return {
            "analytics": {
                "total_subscriptions": total_subs,
                "active_subscriptions": active_subs,
                "trial_subscriptions": trial_subs,
                "cancelled_subscriptions": cancelled_subs,
                "monthly_revenue": round(monthly_rev, 2),
                "yearly_revenue": round(yearly_rev, 2),
                "total_mrr": round(monthly_rev + (yearly_rev / 12), 2),  # Monthly Recurring Revenue
                "churn_rate": round(churn_rate, 2),
                "growth_rate": round(growth_rate, 2)
            },
            "period": {
                "start": thirty_days_ago.isoformat(),
                "end": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analytics: {str(e)}"
        )


@router.get("/admin/revenue/today", response_model=Dict[str, Any])
async def get_today_revenue(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get today's revenue (Super Admin only)

    Calculates total revenue from completed payments processed today.
    """
    try:
        from datetime import date, datetime, timezone

        # Get today's date range (UTC)
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Query completed payments processed today
        today_payments = db.query(Payment).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.processed_at >= today_start,
                Payment.processed_at <= today_end
            )
        ).all()

        # Calculate total revenue
        revenue_today = sum(float(payment.amount) for payment in today_payments)
        payment_count = len(today_payments)

        # Get breakdown by transaction type
        revenue_by_type = {}
        for payment in today_payments:
            trans_type = payment.transaction_type or 'unknown'
            revenue_by_type[trans_type] = revenue_by_type.get(trans_type, 0) + float(payment.amount)

        return {
            "revenue_today": round(revenue_today, 2),
            "payment_count": payment_count,
            "date": today.isoformat(),
            "breakdown": {
                "by_transaction_type": revenue_by_type
            },
            "period": {
                "start": today_start.isoformat(),
                "end": today_end.isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve today's revenue: {str(e)}"
        )


@router.get("/admin/subscriptions", response_model=Dict[str, Any])
async def list_all_subscriptions(
    status_filter: Optional[SubscriptionStatus] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all subscriptions (Admin only)"""
    
    try:
        query = db.query(Subscription)
        
        if status_filter:
            query = query.filter(Subscription.status == status_filter)
        
        subscriptions = query.order_by(Subscription.created_at.desc()).offset(offset).limit(limit).all()
        total_count = query.count()
        
        return {
            "subscriptions": [
                {
                    "id": sub.id,
                    "tenant_id": sub.tenant_id,
                    "plan_id": sub.plan_id,
                    "status": sub.status,
                    "billing_cycle": sub.billing_cycle,
                    "amount": str(sub.amount),
                    "currency": sub.currency,
                    "starts_at": sub.starts_at.isoformat(),
                    "ends_at": sub.ends_at.isoformat(),
                    "created_at": sub.created_at.isoformat()
                }
                for sub in subscriptions
            ],
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve subscriptions: {str(e)}"
        )