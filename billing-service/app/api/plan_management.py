"""
Plan Management API Endpoints

Handles subscription plan changes:
- Upgrades (immediate with proration)
- Downgrades (scheduled for period end)
- Plan change previews
- Subscription cancellation
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..services.dependencies import validate_token, TokenClaims
from ..services.plan_management_service import PlanManagementService
from ..models.subscription import Subscription

router = APIRouter()


# Request Models
class UpgradeRequest(BaseModel):
    """Request to upgrade subscription"""
    new_plan_id: str = Field(..., description="ID of the plan to upgrade to")


class DowngradeRequest(BaseModel):
    """Request to downgrade subscription"""
    new_plan_id: str = Field(..., description="ID of the plan to downgrade to")
    immediate: bool = Field(False, description="Apply downgrade immediately (default: false, scheduled for period end)")


class CancelRequest(BaseModel):
    """Request to cancel subscription"""
    reason: Optional[str] = Field(None, description="Reason for cancellation")
    cancel_immediately: bool = Field(False, description="Cancel immediately vs. at period end")


# Endpoints
@router.post("/subscriptions/{subscription_id}/upgrade", response_model=Dict[str, Any])
async def upgrade_subscription(
    subscription_id: str,
    upgrade_data: UpgradeRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Upgrade subscription to a higher-tier plan.

    **Features**:
    - Applied immediately
    - Prorated charge for remaining billing period
    - User gains access to new plan features right away

    **Proration Example**:
    - Current plan: $10/month, 15 days remaining
    - New plan: $30/month
    - Proration: ($30 - $10) × (15/30) = $10 charged now
    - Next bill: Full $30 at period renewal

    **Returns**:
    - Upgrade confirmation
    - Proration details
    - Payment requirement (if proration > 0)
    """
    try:
        # Verify subscription belongs to tenant
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only upgrade your own subscriptions"
            )

        # Perform upgrade
        plan_mgmt = PlanManagementService(db)
        result = await plan_mgmt.upgrade_subscription(
            subscription_id=subscription_id,
            new_plan_id=upgrade_data.new_plan_id,
            user_email=claims.email,
            user_full_name=claims.full_name
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upgrade subscription: {str(e)}"
        )


@router.post("/subscriptions/{subscription_id}/downgrade", response_model=Dict[str, Any])
async def downgrade_subscription(
    subscription_id: str,
    downgrade_data: DowngradeRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Downgrade subscription to a lower-tier plan.

    **Features**:
    - Scheduled for end of current billing period (default)
    - User keeps current plan benefits until period ends
    - No immediate charge
    - Can be applied immediately if `immediate: true`

    **Scheduling Example**:
    - Current plan: Pro ($30/month)
    - New plan: Basic ($10/month)
    - Current period ends: Dec 31, 2025
    - Downgrade effective: Jan 1, 2026
    - User keeps Pro features until Dec 31

    **Returns**:
    - Downgrade confirmation
    - Effective date
    - Plan comparison
    """
    try:
        # Verify subscription belongs to tenant
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only downgrade your own subscriptions"
            )

        # Perform downgrade
        plan_mgmt = PlanManagementService(db)
        result = await plan_mgmt.downgrade_subscription(
            subscription_id=subscription_id,
            new_plan_id=downgrade_data.new_plan_id,
            user_email=claims.email,
            user_full_name=claims.full_name,
            immediate=downgrade_data.immediate
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to downgrade subscription: {str(e)}"
        )


@router.get("/subscriptions/{subscription_id}/preview-change/{new_plan_id}", response_model=Dict[str, Any])
async def preview_plan_change(
    subscription_id: str,
    new_plan_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Preview the impact of changing to a different plan.

    **Shows**:
    - Current vs. new plan features
    - Proration amount
    - Effective date
    - Whether payment is required
    - Feature changes

    **Use this endpoint to show users exactly what will happen before they commit to a plan change.**

    **Returns**:
    - Complete preview with pricing and feature comparison
    """
    try:
        # Verify subscription belongs to tenant
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only preview changes for your own subscriptions"
            )

        # Get preview
        plan_mgmt = PlanManagementService(db)
        preview = plan_mgmt.preview_plan_change(
            subscription_id=subscription_id,
            new_plan_id=new_plan_id
        )

        return preview

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview plan change: {str(e)}"
        )


@router.post("/subscriptions/{subscription_id}/cancel", response_model=Dict[str, Any])
async def cancel_subscription(
    subscription_id: str,
    cancel_data: CancelRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Cancel a subscription.

    **Cancellation Options**:
    - **At period end** (default): User retains access until current period ends
    - **Immediate**: Access revoked immediately (rare)

    **What happens**:
    - Auto-renewal is disabled
    - Cancellation is logged with reason
    - User receives confirmation email
    - Access continues until effective date

    **Returns**:
    - Cancellation confirmation
    - Effective date
    - Access expiration date
    """
    try:
        # Verify subscription belongs to tenant
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own subscriptions"
            )

        # Perform cancellation
        plan_mgmt = PlanManagementService(db)
        result = await plan_mgmt.cancel_subscription(
            subscription_id=subscription_id,
            reason=cancel_data.reason,
            cancel_immediately=cancel_data.cancel_immediately,
            user_email=claims.email,
            user_full_name=claims.full_name
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.post("/subscriptions/{subscription_id}/reactivate", response_model=Dict[str, Any])
async def reactivate_subscription(
    subscription_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Reactivate a subscription that was scheduled for cancellation.

    **Requirements**:
    - Subscription must have `cancel_at_period_end = true`
    - Current period must not have ended yet

    **What happens**:
    - `cancel_at_period_end` is set to false
    - Auto-renewal is re-enabled
    - Subscription will continue at next billing date

    **Returns**:
    - Reactivation confirmation
    - Next billing date
    """
    try:
        # Verify subscription belongs to tenant
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        if subscription.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only reactivate your own subscriptions"
            )

        if not subscription.cancel_at_period_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription is not scheduled for cancellation"
            )

        # Reactivate
        subscription.cancel_at_period_end = False
        subscription.auto_renew = True
        subscription.cancellation_reason = None
        db.commit()

        return {
            "success": True,
            "message": "Subscription reactivated successfully",
            "subscription_id": subscription.id,
            "next_billing_date": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "auto_renew": True
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reactivate subscription: {str(e)}"
        )
