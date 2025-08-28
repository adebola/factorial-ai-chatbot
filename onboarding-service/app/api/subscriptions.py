from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from ..core.database import get_db
from ..services.dependencies import get_current_tenant, get_admin_tenant
from ..services.subscription_service import SubscriptionService
from ..services.plan_service import PlanService
from ..models.tenant import Tenant
from ..models.subscription import (
    Subscription, SubscriptionStatus, BillingCycle, UsageTracking,
    SubscriptionChange, PaymentMethodRecord
)

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


@router.get("/usage/current", response_model=Dict[str, Any])
async def get_current_usage(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get current usage statistics for the tenant"""
    
    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Get plan limits
        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        
        # Get current usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()
        
        if not usage:
            # Initialize usage tracking if not exists
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()
        
        # Calculate usage percentages
        doc_percentage = (usage.documents_used / plan.document_limit * 100) if plan.document_limit > 0 else 0
        website_percentage = (usage.websites_used / plan.website_limit * 100) if plan.website_limit > 0 else 0
        daily_chat_percentage = (usage.daily_chats_used / plan.daily_chat_limit * 100) if plan.daily_chat_limit > 0 else 0
        monthly_chat_percentage = (usage.monthly_chats_used / plan.monthly_chat_limit * 100) if plan.monthly_chat_limit > 0 else 0
        
        return {
            "usage_statistics": {
                "documents": {
                    "used": usage.documents_used,
                    "limit": plan.document_limit,
                    "percentage": round(doc_percentage, 2),
                    "remaining": max(0, plan.document_limit - usage.documents_used)
                },
                "websites": {
                    "used": usage.websites_used,
                    "limit": plan.website_limit,
                    "percentage": round(website_percentage, 2),
                    "remaining": max(0, plan.website_limit - usage.websites_used)
                },
                "daily_chats": {
                    "used": usage.daily_chats_used,
                    "limit": plan.daily_chat_limit,
                    "percentage": round(daily_chat_percentage, 2),
                    "remaining": max(0, plan.daily_chat_limit - usage.daily_chats_used),
                    "resets_at": usage.daily_reset_at.isoformat() if usage.daily_reset_at else None
                },
                "monthly_chats": {
                    "used": usage.monthly_chats_used,
                    "limit": plan.monthly_chat_limit,
                    "percentage": round(monthly_chat_percentage, 2),
                    "remaining": max(0, plan.monthly_chat_limit - usage.monthly_chats_used),
                    "resets_at": usage.monthly_reset_at.isoformat() if usage.monthly_reset_at else None
                },
                "api_calls": {
                    "used": usage.api_calls_made,
                    "unlimited": True  # Assuming unlimited API calls for now
                }
            },
            "billing_period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat(),
                "days_remaining": (usage.period_end - datetime.utcnow()).days
            },
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Increment usage counter for a specific metric"""
    
    try:
        subscription_service = SubscriptionService(db)
        
        # Get current subscription
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
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
        
        usage.updated_at = datetime.utcnow()
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Check if tenant can perform an action based on usage limits"""
    
    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)
        
        # Get current subscription and plan
        subscription = subscription_service.get_subscription_by_tenant(current_tenant.id)
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
        if usage_type == "documents":
            allowed = usage.documents_used < plan.document_limit
            current = usage.documents_used
            limit = plan.document_limit
        elif usage_type == "websites":
            allowed = usage.websites_used < plan.website_limit
            current = usage.websites_used
            limit = plan.website_limit
        elif usage_type == "daily_chats":
            allowed = usage.daily_chats_used < plan.daily_chat_limit
            current = usage.daily_chats_used
            limit = plan.daily_chat_limit
        elif usage_type == "monthly_chats":
            allowed = usage.monthly_chats_used < plan.monthly_chat_limit
            current = usage.monthly_chats_used
            limit = plan.monthly_chat_limit
        elif usage_type == "api_calls":
            allowed = True  # Assuming unlimited API calls
            current = usage.api_calls_made
            limit = -1  # Unlimited
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription change history for the tenant"""
    
    try:
        changes = db.query(SubscriptionChange).filter(
            SubscriptionChange.tenant_id == current_tenant.id
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


@router.get("/payment-methods", response_model=Dict[str, Any])
async def get_payment_methods(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get saved payment methods for the tenant"""
    
    try:
        payment_methods = db.query(PaymentMethodRecord).filter(
            PaymentMethodRecord.tenant_id == current_tenant.id,
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete a saved payment method"""
    
    try:
        payment_method = db.query(PaymentMethodRecord).filter(
            PaymentMethodRecord.id == method_id,
            PaymentMethodRecord.tenant_id == current_tenant.id
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


# Admin endpoints
@router.get("/admin/analytics", response_model=Dict[str, Any])
async def get_subscription_analytics(
    admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get subscription analytics (Admin only)"""
    
    try:
        # Get subscription counts
        total_subs = db.query(Subscription).count()
        active_subs = db.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.ACTIVE
        ).count()
        trial_subs = db.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.TRIALING
        ).count()
        cancelled_subs = db.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.CANCELLED
        ).count()
        
        # Calculate revenue (simplified)
        monthly_revenue = db.query(Subscription).filter(
            and_(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
                Subscription.billing_cycle == BillingCycle.MONTHLY
            )
        ).all()
        
        yearly_revenue = db.query(Subscription).filter(
            and_(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
                Subscription.billing_cycle == BillingCycle.YEARLY
            )
        ).all()
        
        monthly_rev = sum(float(sub.amount) for sub in monthly_revenue)
        yearly_rev = sum(float(sub.amount) for sub in yearly_revenue)
        
        # Calculate churn rate (simplified - last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        churned_count = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.CANCELLED,
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
                "end": datetime.utcnow().isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analytics: {str(e)}"
        )


@router.get("/admin/subscriptions", response_model=Dict[str, Any])
async def list_all_subscriptions(
    status_filter: Optional[SubscriptionStatus] = None,
    limit: int = 50,
    offset: int = 0,
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                    "status": sub.status.value,
                    "billing_cycle": sub.billing_cycle.value,
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