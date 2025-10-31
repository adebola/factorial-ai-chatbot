"""
Usage Limit Check API

Provides endpoints for other services to check usage limits before performing actions.
Used in the event-driven architecture where services check limits synchronously
before executing operations.
"""

from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.subscription import UsageTracking, Subscription
from ..services.dependencies import TokenClaims, validate_token
from ..services.plan_service import PlanService
from ..services.subscription_service import SubscriptionService

router = APIRouter()


# Request/Response models
class LimitCheckResponse(BaseModel):
    """Response for limit check requests"""
    allowed: bool = Field(..., description="Whether the action is allowed")
    usage_type: str = Field(..., description="Type of usage being checked")
    current_usage: int = Field(..., description="Current usage count")
    limit: int = Field(..., description="Maximum allowed usage (-1 for unlimited)")
    remaining: int = Field(..., description="Remaining usage (-1 for unlimited)")
    unlimited: bool = Field(..., description="Whether this resource is unlimited")
    reason: str = Field(None, description="Reason if not allowed")


class BatchLimitCheckRequest(BaseModel):
    """Request to check multiple usage types at once"""
    usage_types: list[str] = Field(..., description="List of usage types to check")


class BatchLimitCheckResponse(BaseModel):
    """Response for batch limit checks"""
    checks: Dict[str, LimitCheckResponse] = Field(..., description="Limit check results per usage type")
    all_allowed: bool = Field(..., description="Whether all checks passed")


@router.get("/check/{usage_type}", response_model=LimitCheckResponse)
async def check_usage_limit(
    usage_type: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> LimitCheckResponse:
    """
    Check if tenant can perform an action based on usage limits.

    This endpoint is called by other services (onboarding, chat) before
    performing actions that consume resources.

    Supported usage_types:
    - documents: Check document upload limit
    - websites: Check website ingestion limit
    - daily_chats: Check daily chat limit
    - monthly_chats: Check monthly chat limit
    """

    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)

        # Get current subscription and plan
        subscription = subscription_service.get_subscription_by_tenant(claims.tenant_id)
        if not subscription:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="No active subscription found"
            )

        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason="Plan not found"
            )

        # Get usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # Initialize usage tracking if not exists
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

        # Check limits based on usage type
        # Note: limit of -1 means unlimited
        if usage_type == "documents":
            current = usage.documents_used
            limit = plan.document_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "websites":
            current = usage.websites_used
            limit = plan.website_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "daily_chats":
            current = usage.daily_chats_used
            limit = plan.daily_chat_limit
            allowed = (limit == -1) or (current < limit)
        elif usage_type == "monthly_chats":
            current = usage.monthly_chats_used
            limit = plan.monthly_chat_limit
            allowed = (limit == -1) or (current < limit)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid usage type: {usage_type}"
            )

        return LimitCheckResponse(
            allowed=allowed,
            usage_type=usage_type,
            current_usage=current,
            limit=limit,
            remaining=max(0, limit - current) if limit > 0 else -1,
            unlimited=limit == -1,
            reason=None if allowed else f"{usage_type.replace('_', ' ').title()} limit exceeded"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check usage limit: {str(e)}"
        )


@router.post("/check-batch", response_model=BatchLimitCheckResponse)
async def check_batch_limits(
    request: BatchLimitCheckRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> BatchLimitCheckResponse:
    """
    Check multiple usage limits at once.

    Useful when a service needs to check multiple limits before proceeding
    (e.g., checking both daily and monthly chat limits).
    """

    checks = {}
    all_allowed = True

    for usage_type in request.usage_types:
        try:
            check_result = await check_usage_limit(usage_type, claims, db)
            checks[usage_type] = check_result
            if not check_result.allowed:
                all_allowed = False
        except HTTPException as e:
            # If a check fails, mark as not allowed
            checks[usage_type] = LimitCheckResponse(
                allowed=False,
                usage_type=usage_type,
                current_usage=0,
                limit=0,
                remaining=0,
                unlimited=False,
                reason=e.detail
            )
            all_allowed = False

    return BatchLimitCheckResponse(
        checks=checks,
        all_allowed=all_allowed
    )


@router.get("/stats/{tenant_id}", response_model=Dict[str, Any])
async def get_usage_stats(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get current usage statistics for a tenant.

    This is a lightweight endpoint for getting raw usage numbers.
    For detailed usage with percentages and limits, use /subscriptions/usage/current
    """

    # Verify tenant access (users can only access their own tenant data)
    if claims.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant's usage data"
        )

    try:
        subscription_service = SubscriptionService(db)

        # Get subscription
        subscription = subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return {
                "tenant_id": tenant_id,
                "has_subscription": False,
                "usage": {
                    "documents_used": 0,
                    "websites_used": 0,
                    "daily_chats_used": 0,
                    "monthly_chats_used": 0,
                    "api_calls_made": 0
                }
            }

        # Get usage tracking
        usage = db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()

        if not usage:
            # Initialize if not exists
            subscription_service._initialize_usage_tracking(subscription)
            usage = db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

        return {
            "tenant_id": tenant_id,
            "has_subscription": True,
            "subscription_id": subscription.id,
            "usage": {
                "documents_used": usage.documents_used,
                "websites_used": usage.websites_used,
                "daily_chats_used": usage.daily_chats_used,
                "monthly_chats_used": usage.monthly_chats_used,
                "api_calls_made": usage.api_calls_made
            },
            "resets": {
                "daily_reset_at": usage.daily_reset_at.isoformat() if usage.daily_reset_at else None,
                "monthly_reset_at": usage.monthly_reset_at.isoformat() if usage.monthly_reset_at else None
            },
            "period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat()
            },
            "updated_at": usage.updated_at.isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve usage stats: {str(e)}"
        )


@router.post("/increment/{usage_type}", response_model=Dict[str, Any])
async def increment_usage(
    usage_type: str,
    amount: int = 1,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Increment usage counter for a specific metric.

    NOTE: In the event-driven architecture, this endpoint is primarily used
    for manual adjustments or testing. Normal usage increments should happen
    via the RabbitMQ consumer processing usage events.

    Supported usage_types:
    - documents: Increment document count
    - websites: Increment website count
    - daily_chats: Increment daily chat count
    - monthly_chats: Increment monthly chat count
    - api_calls: Increment API call count
    """

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
                detail=f"Invalid usage type: {usage_type}"
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
