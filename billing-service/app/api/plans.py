from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..models.plan import Plan
from ..services.dependencies import TokenClaims, validate_token, logger
from ..services.plan_service import PlanService

router = APIRouter()


def format_plan_features(plan: Plan) -> Dict[str, Any]:
    """Format plan features for UI display"""
    import json

    # Parse support_channels if it's a JSON string
    support_channels = plan.support_channels
    if isinstance(support_channels, str):
        try:
            support_channels = json.loads(support_channels)
        except (json.JSONDecodeError, TypeError):
            support_channels = ["Email"]
    elif not support_channels:
        support_channels = ["Email"]

    # Capitalize the first letter of each channel for UI display
    support_channels = [channel.capitalize() if isinstance(channel, str) else channel
                       for channel in support_channels]

    return {
        "conversational_workflow": plan.has_conversational_workflow,
        "sentiment_analytics": plan.has_sentiment_analysis,
        "api_access": plan.has_api_access,
        "custom_integrations": plan.has_custom_integrations,
        "on_premise": plan.has_on_premise,
        "analytics_level": plan.analytics_level,
        "support_channels": support_channels
    }


# Pydantic models for request/response
class PlanCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    document_limit: int = Field(default=10, ge=0)
    website_limit: int = Field(default=1, ge=0)
    daily_chat_limit: int = Field(default=50, ge=0)
    monthly_chat_limit: int = Field(default=1500, ge=0)
    monthly_plan_cost: Decimal = Field(default=Decimal('0.00'), ge=0)
    yearly_plan_cost: Decimal = Field(default=Decimal('0.00'), ge=0)
    features: Optional[Dict[str, Any]] = None


class PlanUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    document_limit: Optional[int] = Field(None, ge=0)
    website_limit: Optional[int] = Field(None, ge=0)
    daily_chat_limit: Optional[int] = Field(None, ge=0)
    monthly_chat_limit: Optional[int] = Field(None, ge=0)
    monthly_plan_cost: Optional[Decimal] = Field(None, ge=0)
    yearly_plan_cost: Optional[Decimal] = Field(None, ge=0)
    features: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    document_limit: int
    website_limit: int
    daily_chat_limit: int
    monthly_chat_limit: int
    monthly_plan_cost: Decimal
    yearly_plan_cost: Decimal
    features: Dict[str, Any]
    is_active: bool
    is_deleted: bool
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


@router.post("/plans/", response_model=Dict[str, Any])
async def create_plan(
    plan_data: PlanCreateRequest,
    claims: TokenClaims = Depends(validate_token),
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create a new plan (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        plan = plan_service.create_plan(
            name=plan_data.name,
            description=plan_data.description,
            document_limit=plan_data.document_limit,
            website_limit=plan_data.website_limit,
            daily_chat_limit=plan_data.daily_chat_limit,
            monthly_chat_limit=plan_data.monthly_chat_limit,
            monthly_plan_cost=plan_data.monthly_plan_cost,
            yearly_plan_cost=plan_data.yearly_plan_cost,
            features=plan_data.features or {}
        )

        # Invalidate plan caches after creation
        try:
            from ..services.cache_service import CacheService
            cache_service = CacheService()
            await cache_service.invalidate_all_plans_cache()
            logger.info("Invalidated plan caches after creating new plan")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate plan cache after creation: {cache_error}")
        
        return {
            "message": "Plan created successfully",
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "document_limit": plan.document_limit,
                "website_limit": plan.website_limit,
                "daily_chat_limit": plan.daily_chat_limit,
                "monthly_chat_limit": plan.monthly_chat_limit,
                "monthly_plan_cost": str(plan.monthly_plan_cost),
                "yearly_plan_cost": str(plan.yearly_plan_cost),
                "features": plan.features,
                "is_active": plan.is_active,
                "created_at": plan.created_at.isoformat()
            },
            "created_by": {
                "admin_id": claims.tenant_id,
                "admin_username":claims.tenant_id,
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
            detail=f"Failed to create plan: {str(e)}"
        )


@router.get("/plans/public", response_model=Dict[str, Any])
async def list_public_plans(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all active plans (public endpoint for dashboards/signup pages)"""

    try:
        plan_service = PlanService(db)
        plans = plan_service.get_all_plans(include_deleted=False, active_only=True)

        return {
            "plans": [
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": plan.description,
                    "document_limit": plan.document_limit,
                    "website_limit": plan.website_limit,
                    "daily_chat_limit": plan.daily_chat_limit,
                    "monthly_chat_limit": plan.monthly_chat_limit,
                    "max_document_size_mb": plan.max_document_size_mb,
                    "max_pages_per_website": plan.max_pages_per_website,
                    "monthly_plan_cost": str(plan.monthly_plan_cost),
                    "yearly_plan_cost": str(plan.yearly_plan_cost),
                    "has_trial": plan.has_trial,
                    "trial_days": plan.trial_days,
                    "features": format_plan_features(plan),
                    "is_active": plan.is_active,
                    "created_at": plan.created_at.isoformat()
                }
                for plan in plans
            ],
            "total_plans": len(plans),
            "message": "Active subscription plans available for signup"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve public plans: {str(e)}"
        )


@router.get("/plans/", response_model=Dict[str, Any])
async def list_plans(
    include_deleted: bool = False,
    active_only: bool = False,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all plans (accessible to all authenticated users)"""
    
    try:
        plan_service = PlanService(db)
        plans = plan_service.get_all_plans(
            # include_deleted=include_deleted and current_tenant.role.value == "admin",
            active_only=active_only
        )
        
        return {
            "plans": [
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": plan.description,
                    "document_limit": plan.document_limit,
                    "website_limit": plan.website_limit,
                    "daily_chat_limit": plan.daily_chat_limit,
                    "monthly_chat_limit": plan.monthly_chat_limit,
                    "monthly_plan_cost": str(plan.monthly_plan_cost),
                    "yearly_plan_cost": str(plan.yearly_plan_cost),
                    "features": plan.features,
                    "is_active": plan.is_active,
                    "is_deleted": plan.is_deleted,
                    "created_at": plan.created_at.isoformat(),
                    "updated_at": plan.updated_at.isoformat() if plan.updated_at else None
                }
                for plan in plans
            ],
            "total_plans": len(plans),
            "filters": {
                "include_deleted": include_deleted,
                "active_only": active_only
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve plans: {str(e)}"
        )


@router.get("/plans/free-tier", dependencies=[])
async def get_free_tier_plan(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get the free-tier plan information for tenant creation.
    This endpoint is used by the authorization server when creating new tenants.
    PUBLIC ENDPOINT - No authentication required.
    """
    from ..services.cache_service import CacheService
    import logging

    logger = logging.getLogger(__name__)

    try:
        cache_service = CacheService()

        # Try to get from cache first using the new cache key format
        cached_plan = await cache_service.get_free_tier_plan()
        if cached_plan:
            logger.debug("Retrieved free-tier plan from cache")
            return cached_plan

        # Not in cache, get from the database
        free_plan = db.query(Plan).filter(
            Plan.name == "Basic",
            Plan.is_active == True,
            Plan.is_deleted == False
        ).first()

        if not free_plan:
            logger.error("Free-tier plan not found in database")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Free-tier plan not found. Please ensure default plans are created."
            )

        # Prepare response data
        plan_data = {
            "id": free_plan.id,
            "name": free_plan.name,
            "description": free_plan.description,
            "document_limit": free_plan.document_limit,
            "website_limit": free_plan.website_limit,
            "daily_chat_limit": free_plan.daily_chat_limit,
            "monthly_chat_limit": free_plan.monthly_chat_limit,
            "monthly_plan_cost": str(free_plan.monthly_plan_cost),
            "yearly_plan_cost": str(free_plan.yearly_plan_cost),
            "features": free_plan.features,
            "is_active": free_plan.is_active,
            "created_at": free_plan.created_at.isoformat(),
            "updated_at": free_plan.updated_at.isoformat() if free_plan.updated_at else None
        }

        # Cache using the new cache service method
        await cache_service.cache_free_tier_plan(plan_data)
        logger.info("Cached free-tier plan for 1 hour using onboarding service cache manager")

        return plan_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve free-tier plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve free-tier plan: {str(e)}"
        )


@router.get("/plans/{plan_id}", response_model=Dict[str, Any])
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get a specific plan by ID"""
    
    try:
        plan_service = PlanService(db)
        plan = plan_service.get_plan_by_id(
            plan_id
        )
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        # Get usage stats if admin
        # usage_stats = None
        # if current_tenant.role.value == "admin":
        usage_stats = plan_service.get_plan_usage_stats(plan_id)
        
        response = {
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "document_limit": plan.document_limit,
                "website_limit": plan.website_limit,
                "daily_chat_limit": plan.daily_chat_limit,
                "monthly_chat_limit": plan.monthly_chat_limit,
                "monthly_plan_cost": str(plan.monthly_plan_cost),
                "yearly_plan_cost": str(plan.yearly_plan_cost),
                "features": plan.features,
                "is_active": plan.is_active,
                "is_deleted": plan.is_deleted,
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat() if plan.updated_at else None
            }
        }
        
        if usage_stats:
            response["usage_stats"] = usage_stats
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve plan: {str(e)}"
        )


@router.put("/plans/{plan_id}", response_model=Dict[str, Any])
async def update_plan(
    plan_id: str,
    plan_data: PlanUpdateRequest,
    claims: TokenClaims = Depends(validate_token),
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Update an existing plan (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        
        # Prepare update data (only include non-None fields)
        update_data = {
            k: v for k, v in plan_data.dict().items() 
            if v is not None
        }
        
        plan = plan_service.update_plan(plan_id, **update_data)

        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )

        # Invalidate plan caches after update
        try:
            from ..services.cache_service import CacheService
            cache_service = CacheService()
            await cache_service.invalidate_plan_by_id(plan_id)
            if plan.name == "Free":
                await cache_service.invalidate_free_tier_plan()
            await cache_service.invalidate_all_plans_cache()
            logger.info(f"Invalidated plan caches after updating plan: {plan_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate plan cache after update: {cache_error}")
        
        return {
            "message": "Plan updated successfully",
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "document_limit": plan.document_limit,
                "website_limit": plan.website_limit,
                "daily_chat_limit": plan.daily_chat_limit,
                "monthly_chat_limit": plan.monthly_chat_limit,
                "monthly_plan_cost": str(plan.monthly_plan_cost),
                "yearly_plan_cost": str(plan.yearly_plan_cost),
                "features": plan.features,
                "is_active": plan.is_active,
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat() if plan.updated_at else None
            },
            "updated_by": {
                "admin_id": claims.tenant_id,
                "admin_username": claims.tenant_id
            }
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
            detail=f"Failed to update plan: {str(e)}"
        )


@router.delete("/plans/{plan_id}", response_model=Dict[str, Any])
async def delete_plan(
    plan_id: str,
    claims: TokenClaims = Depends(validate_token),
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Soft delete a plan (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        plan = plan_service.get_plan_by_id(plan_id)
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        success = plan_service.soft_delete_plan(plan_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete plan"
            )

        # Invalidate plan caches after deletion
        try:
            from ..services.cache_service import CacheService
            cache_service = CacheService()
            await cache_service.invalidate_plan_by_id(plan_id)
            if plan.name == "Free":
                await cache_service.invalidate_free_tier_plan()
            await cache_service.invalidate_all_plans_cache()
            logger.info(f"Invalidated plan caches after deleting plan: {plan_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate plan cache after deletion: {cache_error}")
        
        return {
            "message": f"Plan '{plan.name}' deleted successfully",
            "plan_id": plan_id,
            "plan_name": plan.name,
            "deleted_by": {
                "admin_id": claims.tenant_id,
                "admin_username": claims.tenant_id
            }
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
            detail=f"Failed to delete plan: {str(e)}"
        )


@router.post("/plans/{plan_id}/restore", response_model=Dict[str, Any])
async def restore_plan(
    plan_id: str,
    claims: TokenClaims = Depends(validate_token),
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Restore a soft-deleted plan (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        plan = plan_service.get_plan_by_id(plan_id, include_deleted=True)
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        if not plan.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plan is not deleted"
            )
        
        success = plan_service.restore_plan(plan_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to restore plan"
            )
        
        return {
            "message": f"Plan '{plan.name}' restored successfully",
            "plan_id": plan_id,
            "plan_name": plan.name,
            "restored_by": {
                "admin_id": claims.tenant_id,
                "admin_username": claims.tenant_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore plan: {str(e)}"
        )


@router.post("/plans/create-defaults", response_model=Dict[str, Any])
async def create_default_plans(
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create default plans (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        created_plans = plan_service.create_default_plans()
        
        return {
            "message": f"Created {len(created_plans)} default plans",
            "created_plans": [
                {
                    "id": plan.id,
                    "name": plan.name,
                    "monthly_cost": str(plan.monthly_plan_cost)
                }
                for plan in created_plans
            ],
            "created_by": {
                "admin_id": claims.tenant_id,
                "admin_username": claims.tenant_id
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create default plans: {str(e)}"
        )


@router.get("/plans/{plan_id}/usage", response_model=Dict[str, Any])
async def get_plan_usage(
    plan_id: str,
    claims: TokenClaims = Depends(validate_token),
    # admin_tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get usage statistics for a plan (Admin only)"""
    
    try:
        plan_service = PlanService(db)
        usage_stats = plan_service.get_plan_usage_stats(plan_id)
        
        if not usage_stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        return {
            "usage_statistics": usage_stats,
            "requested_by": {
                "admin_id": claims.tenant_id,
                "admin_username":claims.tenant_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan usage: {str(e)}"
        )


# Plan switching endpoints for customers
class PlanSwitchRequest(BaseModel):
    new_plan_id: str = Field(..., description="ID of the plan to switch to")
    billing_cycle: str = Field(default="monthly", description="Billing cycle: 'monthly' or 'yearly'")
    payment_reference: Optional[str] = Field(None, description="Payment reference for upgrades (required if prorated_amount > 0)")


class PlanPreviewRequest(BaseModel):
    new_plan_id: str = Field(..., description="ID of the plan to preview switch to")
    billing_cycle: str = Field(default="monthly", description="Billing cycle: 'monthly' or 'yearly'")


@router.post("/plans/preview-switch", response_model=Dict[str, Any])
async def preview_plan_switch(
    preview_request: PlanPreviewRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Preview plan switch without making changes.
    Returns proration details and whether payment is required.
    """
    from ..services.subscription_service import SubscriptionService
    from ..models.subscription import BillingCycle

    tenant_id = claims.tenant_id
    logger.info(f"Plan switch preview request for tenant: {tenant_id}")

    try:
        plan_service = PlanService(db)
        subscription_service = SubscriptionService(db)

        # Get current subscription
        existing_subscription = subscription_service.get_subscription_by_tenant(tenant_id)
        if not existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found. Cannot preview plan switch."
            )

        # Validate new plan exists and is active
        new_plan = plan_service.get_plan_by_id(preview_request.new_plan_id)
        if not new_plan or not new_plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan or plan is not active"
            )

        # Get current plan
        current_plan = plan_service.get_plan_by_id(existing_subscription.plan_id)
        if not current_plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current plan not found"
            )

        # ENTERPRISE PLAN: Require manual contact
        if new_plan.name == "Enterprise":
            return {
                "requires_payment": False,
                "action_required": "contact_sales",
                "message": "Please contact ChatCraft Support for Enterprise plan",
                "contact_info": {
                    "phone_numbers": ["+2348182222236", "+2348052222236"],
                    "email": "sales@chatcraft.cc"
                }
            }

        if current_plan.name == "Enterprise":
            return {
                "requires_payment": False,
                "action_required": "contact_sales",
                "message": "Please contact ChatCraft Support to change from Enterprise plan",
                "contact_info": {
                    "phone_numbers": ["+2348182222236", "+2348052222236"],
                    "email": "sales@chatcraft.cc"
                }
            }

        # Same plan check
        if existing_subscription.plan_id == new_plan.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You are already subscribed to the {new_plan.name} plan"
            )

        # Determine billing cycle
        billing_cycle = BillingCycle.YEARLY if preview_request.billing_cycle.lower() == "yearly" else BillingCycle.MONTHLY

        # Calculate costs
        old_cost = current_plan.yearly_plan_cost if billing_cycle == BillingCycle.YEARLY else current_plan.monthly_plan_cost
        new_cost = new_plan.yearly_plan_cost if billing_cycle == BillingCycle.YEARLY else new_plan.monthly_plan_cost

        is_upgrade = new_cost > old_cost
        is_downgrade = new_cost < old_cost

        # Calculate payment amount for upgrades
        # For trial upgrades: charge full monthly/yearly amount
        # For paid-to-paid upgrades: prorate based on remaining days
        from ..models.subscription import SubscriptionStatus
        is_trial_upgrade = existing_subscription.status == SubscriptionStatus.TRIALING

        prorated_amount = 0
        if is_upgrade:
            if is_trial_upgrade:
                # Trial upgrade: charge full amount (no proration)
                prorated_amount = float(new_cost)
            elif existing_subscription.current_period_end:
                # Paid-to-paid upgrade: prorate based on remaining days
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                period_end = existing_subscription.current_period_end
                if period_end.tzinfo is None:
                    period_end = period_end.replace(tzinfo=timezone.utc)

                # Calculate remaining days in current period
                remaining_days = (period_end - now).days
                if remaining_days > 0:
                    # Calculate daily rate difference
                    days_in_period = 30 if billing_cycle == BillingCycle.MONTHLY else 365
                    daily_rate_diff = (float(new_cost) - float(old_cost)) / days_in_period
                    prorated_amount = round(daily_rate_diff * remaining_days, 2)

        return {
            "preview": {
                "current_plan": {
                    "id": current_plan.id,
                    "name": current_plan.name,
                    "cost": float(old_cost)
                },
                "new_plan": {
                    "id": new_plan.id,
                    "name": new_plan.name,
                    "cost": float(new_cost),
                    "description": new_plan.description,
                    "document_limit": new_plan.document_limit,
                    "website_limit": new_plan.website_limit,
                    "daily_chat_limit": new_plan.daily_chat_limit,
                    "monthly_chat_limit": new_plan.monthly_chat_limit
                },
                "billing_cycle": preview_request.billing_cycle
            },
            "billing_info": {
                "old_cost": float(old_cost),
                "new_cost": float(new_cost),
                "prorated_amount": prorated_amount,
                "is_upgrade": is_upgrade,
                "is_downgrade": is_downgrade,
                "currency": existing_subscription.currency or "NGN"
            },
            "requires_payment": is_upgrade and prorated_amount > 0,
            "effective_immediately": is_upgrade,
            "scheduled_for_period_end": is_downgrade,
            "message": (
                f"{'Trial upgrade' if is_trial_upgrade else 'Upgrade'} to {new_plan.name} requires payment of {prorated_amount} {existing_subscription.currency or 'NGN'}. "
                f"{'You will receive a full 30-day subscription period.' if is_trial_upgrade and billing_cycle == BillingCycle.MONTHLY else ''}"
                f"{'You will receive a full 365-day subscription period.' if is_trial_upgrade and billing_cycle == BillingCycle.YEARLY else ''}"
                if is_upgrade and prorated_amount > 0
                else f"Switch to {new_plan.name} will take effect {'immediately' if is_upgrade else 'at the end of your current billing period'}"
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview plan switch for tenant {tenant_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview plan switch: {str(e)}"
        )


@router.post("/plans/switch", response_model=Dict[str, Any])
async def switch_tenant_plan(
    plan_switch: PlanSwitchRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Switch tenant's plan (authenticated user can switch their own plan)

    Logic:
    - If user has no subscription: Create Basic plan with 14-day trial from registration
    - If user has subscription: Switch to new plan with proration
    - Update auth server with subscription_id and plan_id via RabbitMQ
    """
    from ..services.subscription_service import SubscriptionService
    from ..services.rabbitmq_service import rabbitmq_service
    from ..services.dependencies import get_full_tenant_details
    from ..models.subscription import BillingCycle
    from dateutil import parser

    tenant_id = claims.tenant_id
    logger.info(f"Plan switch request for tenant: {tenant_id}")

    try:
        plan_service = PlanService(db)
        subscription_service = SubscriptionService(db)

        # Get current tenant info from the auth server
        target_tenant = await get_full_tenant_details(tenant_id, access_token=claims.access_token)
        if not target_tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )

        # Get tenant's registration date for trial calculation
        tenant_created_at = target_tenant.get("createdAt")
        if not tenant_created_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant registration date not found"
            )

        # Parse the registration date (handle ISO8601 formats)
        if isinstance(tenant_created_at, str):
            registration_date = parser.isoparse(tenant_created_at.replace('Z', '+00:00'))
        else:
            registration_date = tenant_created_at

        # Check if the tenant has an active subscription
        existing_subscription = subscription_service.get_subscription_by_tenant(tenant_id)

        # Determine billing cycle
        billing_cycle = BillingCycle.YEARLY if plan_switch.billing_cycle.lower() == "yearly" else BillingCycle.MONTHLY

        if not existing_subscription:
            # SCENARIO 1: No subscription exists - create Basic plan with 14-day trial
            logger.info(f"Tenant {tenant_id} has no subscription. Creating Basic plan with trial.")

            # Get Basic plan by name
            basic_plan = plan_service.get_plan_by_name("Basic")
            if not basic_plan or not basic_plan.is_active:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Basic plan not found or inactive"
                )

            # Calculate trial end date: 14 days from registration
            trial_end_date = registration_date + timedelta(days=14)

            # Check if trial would be in the past - if so, don't use trial
            now = datetime.now(timezone.utc)
            use_trial = trial_end_date > now

            # Create subscription with custom trial end only if trial hasn't expired
            subscription = subscription_service.create_subscription(
                tenant_id=tenant_id,
                plan_id=basic_plan.id,
                billing_cycle=billing_cycle,
                start_trial=use_trial and basic_plan.monthly_plan_cost == 0,  # Only trial for free plans
                custom_trial_end=trial_end_date if use_trial else None,
                metadata={
                    "created_via": "switch_tenant_plan",
                    "user_id": claims.user_id,
                    "initial_plan": True,
                    "trial_skipped": not use_trial,
                    "trial_skipped_reason": "trial_period_expired" if not use_trial else None
                }
            )

            # Publish to RabbitMQ for auth server to update tenant
            rabbitmq_success = rabbitmq_service.publish_plan_update(
                tenant_id=tenant_id,
                subscription_id=subscription.id,
                plan_id=basic_plan.id,
                action="subscription_created"
            )

            if not rabbitmq_success:
                logger.warning(
                    f"Failed to publish subscription creation to RabbitMQ for tenant {tenant_id}. "
                    "Auth server may not be updated."
                )

            return {
                "message": f"Successfully created {basic_plan.name} plan subscription with trial",
                "plan_switch": {
                    "tenant_id": tenant_id,
                    "subscription_id": subscription.id,
                    "action": "subscription_created",
                    "previous_plan": None,
                    "new_plan": {
                        "id": basic_plan.id,
                        "name": basic_plan.name,
                        "description": basic_plan.description,
                        "document_limit": basic_plan.document_limit,
                        "website_limit": basic_plan.website_limit,
                        "daily_chat_limit": basic_plan.daily_chat_limit,
                        "monthly_chat_limit": basic_plan.monthly_chat_limit,
                        "features": basic_plan.features
                    }
                },
                "subscription_info": {
                    "status": subscription.status,
                    "billing_cycle": subscription.billing_cycle,
                    "trial_starts_at": subscription.trial_starts_at.isoformat() if subscription.trial_starts_at else None,
                    "trial_ends_at": subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
                    "starts_at": subscription.starts_at.isoformat() if subscription.starts_at else None,
                    "amount": float(subscription.amount),
                    "currency": subscription.currency
                },
                "effective_immediately": True,
                "rabbitmq_notified": rabbitmq_success
            }

        else:
            # SCENARIO 2: Subscription exists - switch plan with proration
            logger.info(
                f"Tenant {tenant_id} has existing subscription {existing_subscription.id}. "
                f"Switching plan to {plan_switch.new_plan_id}."
            )

            # Validate new plan exists and is active
            new_plan = plan_service.get_plan_by_id(plan_switch.new_plan_id)
            if not new_plan or not new_plan.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid plan or plan is not active"
                )

            # ENTERPRISE PLAN: Require manual contact for upgrade
            if new_plan.name == "Enterprise":
                logger.info(f"Tenant {tenant_id} requested Enterprise plan - returning contact information")
                return {
                    "message": "Please contact ChatCraft Support on +2348182222236 / +2348052222236 or sales@chatcraft.cc for upgrade to Enterprise",
                    "plan_requested": {
                        "id": new_plan.id,
                        "name": new_plan.name,
                        "description": new_plan.description
                    },
                    "contact_info": {
                        "phone_numbers": ["+2348182222236", "+2348052222236"],
                        "email": "sales@chatcraft.cc"
                    },
                    "action_required": "contact_sales"
                }

            # Get current plan for comparison
            current_plan = plan_service.get_plan_by_id(existing_subscription.plan_id)

            # ENTERPRISE PLAN SUBSCRIBER: Cannot switch away from Enterprise plan
            if current_plan and current_plan.name == "Enterprise":
                logger.info(f"Tenant {tenant_id} on Enterprise plan attempted to switch - returning contact information")
                return {
                    "message": "Please contact ChatCraft Support on +2348182222236 / +2348052222236 or sales@chatcraft.cc for upgrade to Enterprise",
                    "current_plan": {
                        "id": current_plan.id,
                        "name": current_plan.name,
                        "description": current_plan.description
                    },
                    "contact_info": {
                        "phone_numbers": ["+2348182222236", "+2348052222236"],
                        "email": "sales@chatcraft.cc"
                    },
                    "action_required": "contact_sales",
                    "note": "All migrations to and from the Enterprise plan can only be done by backend system administrator"
                }

            # VALIDATION: Reject if user is trying to switch to the same plan they already have
            if existing_subscription.plan_id == new_plan.id:
                from ..models.subscription import SubscriptionStatus
                if existing_subscription.status in ['active', 'trialing']:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"You are already subscribed to the {new_plan.name} plan. "
                               f"Your subscription is currently {existing_subscription.status}."
                    )

            # PAYMENT VERIFICATION FOR UPGRADES
            # Calculate if this is an upgrade requiring payment
            old_cost = current_plan.yearly_plan_cost if billing_cycle == BillingCycle.YEARLY else current_plan.monthly_plan_cost
            new_cost = new_plan.yearly_plan_cost if billing_cycle == BillingCycle.YEARLY else new_plan.monthly_plan_cost
            is_upgrade = float(new_cost) > float(old_cost)

            if is_upgrade:
                # Calculate payment amount
                # For trial upgrades: charge full monthly/yearly amount
                # For paid-to-paid upgrades: prorate based on remaining days
                from ..models.subscription import SubscriptionStatus
                is_trial_upgrade = existing_subscription.status == SubscriptionStatus.TRIALING

                if is_trial_upgrade:
                    # Trial upgrade: charge full amount (no proration)
                    prorated_amount = float(new_cost)
                    logger.info(
                        f"Trial upgrade for tenant {tenant_id}: charging full amount {prorated_amount} "
                        f"(no proration for trial-to-paid upgrades)"
                    )
                else:
                    # Paid-to-paid upgrade: prorate based on remaining days
                    prorated_amount = 0
                    if existing_subscription.current_period_end:
                        now = datetime.now(timezone.utc)
                        period_end = existing_subscription.current_period_end
                        if period_end.tzinfo is None:
                            period_end = period_end.replace(tzinfo=timezone.utc)

                        remaining_days = (period_end - now).days
                        if remaining_days > 0:
                            days_in_period = 30 if billing_cycle == BillingCycle.MONTHLY else 365
                            daily_rate_diff = (float(new_cost) - float(old_cost)) / days_in_period
                            prorated_amount = round(daily_rate_diff * remaining_days, 2)

                # Require payment for upgrades with prorated amount > 0
                if prorated_amount > 0:
                    if not plan_switch.payment_reference:
                        raise HTTPException(
                            status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail={
                                "message": "Payment required for upgrade",
                                "prorated_amount": prorated_amount,
                                "currency": existing_subscription.currency or "NGN",
                                "requires_payment": True,
                                "hint": "Use /plans/preview-switch to get proration details, then complete payment before switching"
                            }
                        )

                    # Verify payment with Paystack
                    from ..services.paystack_service import PaystackService
                    paystack_service = PaystackService(db)
                    payment_verified = await paystack_service.verify_transaction(plan_switch.payment_reference)

                    if not payment_verified or not payment_verified.get("success") or not payment_verified.get("verified"):
                        error_msg = payment_verified.get("error", "Payment verification failed") if payment_verified else "Payment verification failed"
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Payment verification failed: {error_msg}. Please ensure payment was completed successfully."
                        )

                    # Check payment amount matches expected prorated amount (with 1% tolerance for currency conversion)
                    paid_amount = float(payment_verified.get("amount", 0))  # Amount already converted from kobo
                    if abs(paid_amount - prorated_amount) > (prorated_amount * 0.01):
                        logger.warning(
                            f"Payment amount mismatch for tenant {tenant_id}: "
                            f"expected {prorated_amount}, got {paid_amount}"
                        )
                        # Allow it to proceed but log the discrepancy

                    logger.info(f"Payment verified for tenant {tenant_id}: reference={plan_switch.payment_reference}")

                    # Create Payment record for successful upgrade payment
                    from ..models.subscription import Payment, PaymentStatus, TransactionType

                    upgrade_payment = Payment(
                        subscription_id=existing_subscription.id,
                        tenant_id=tenant_id,
                        amount=Decimal(str(prorated_amount)),
                        currency=existing_subscription.currency or "NGN",
                        status=PaymentStatus.COMPLETED,  # Already verified with Paystack
                        payment_method=payment_verified.get("channel"),  # card, bank, ussd, etc.
                        transaction_type=TransactionType.UPGRADE,

                        # Paystack details
                        paystack_reference=plan_switch.payment_reference,
                        paystack_access_code=None,  # Not available in verify response
                        paystack_transaction_id=str(payment_verified.get("transaction_id")),

                        # Processing details
                        gateway_response=payment_verified.get("data", {}),
                        processed_at=datetime.now(timezone.utc),

                        # Description
                        description=f"Plan upgrade from {current_plan.name if current_plan else 'Free'} to {new_plan.name}",

                        # Metadata
                        payment_metadata={
                            "old_plan_id": current_plan.id if current_plan else None,
                            "old_plan_name": current_plan.name if current_plan else "Free",
                            "new_plan_id": new_plan.id,
                            "new_plan_name": new_plan.name,
                            "billing_cycle": plan_switch.billing_cycle,
                            "is_trial_upgrade": is_trial_upgrade,
                            "paid_at": payment_verified.get("paid_at"),
                            "paystack_customer": payment_verified.get("customer", {}),
                            "paystack_authorization": payment_verified.get("authorization", {})
                        }
                    )

                    # Save to database
                    db.add(upgrade_payment)
                    db.commit()
                    db.refresh(upgrade_payment)

                    logger.info(
                        f"Created payment record {upgrade_payment.id} for plan upgrade: "
                        f"tenant={tenant_id}, amount={prorated_amount}, reference={plan_switch.payment_reference}"
                    )

                    # Generate invoice for upgrade payment
                    try:
                        from ..services.invoice_service import InvoiceService
                        from ..services.pdf_generator import PDFGenerator
                        from ..services.email_publisher import email_publisher

                        invoice_service = InvoiceService(db)
                        invoice, pdf_bytes = invoice_service.create_invoice_with_pdf(
                            upgrade_payment,
                            document_type="invoice"
                        )

                        if invoice:
                            logger.info(f"Created invoice {invoice.invoice_number} for upgrade payment {upgrade_payment.id}")

                            # Send invoice email with PDF attachment
                            pdf_attachment = None
                            if pdf_bytes:
                                pdf_gen = PDFGenerator()
                                pdf_attachment = pdf_gen.generate_attachment_dict(pdf_bytes, invoice.invoice_number)
                                logger.info(f"Generated PDF attachment for invoice {invoice.invoice_number}")

                            email_publisher.publish_invoice_email(
                                tenant_id=existing_subscription.tenant_id,
                                to_email=claims.email,
                                to_name=claims.full_name or "Valued Customer",
                                invoice_number=invoice.invoice_number,
                                total_amount=float(invoice.total_amount),
                                currency=invoice.currency,
                                due_date=invoice.due_date,
                                status=invoice.status,
                                pdf_attachment=pdf_attachment
                            )
                            logger.info(f"Sent invoice email for {invoice.invoice_number} to {claims.email}")
                        else:
                            logger.error(f"Failed to create invoice for upgrade payment {upgrade_payment.id}")

                    except Exception as e:
                        logger.error(
                            f"Failed to generate invoice for upgrade payment {upgrade_payment.id}: {str(e)}",
                            exc_info=True
                        )

            # Switch subscription plan
            switch_result = subscription_service.switch_subscription_plan(
                subscription_id=existing_subscription.id,
                new_plan_id=new_plan.id,
                billing_cycle=billing_cycle,
                prorate=True
            )

            # Update user fields for email notifications (critical for scheduled jobs)
            existing_subscription.user_email = claims.email
            existing_subscription.user_full_name = claims.full_name
            db.commit()
            db.refresh(existing_subscription)
            logger.info(
                f"Updated subscription {existing_subscription.id} with user info: "
                f"email={claims.email}, name={claims.full_name}"
            )

            # Only publish to RabbitMQ if change is effective immediately (not scheduled downgrades)
            rabbitmq_success = False
            if switch_result.get("effective_immediately", True):
                rabbitmq_success = rabbitmq_service.publish_plan_switch(
                    tenant_id=tenant_id,
                    subscription_id=existing_subscription.id,
                    old_plan_id=current_plan.id if current_plan else None,
                    new_plan_id=new_plan.id
                )

                if not rabbitmq_success:
                    logger.warning(
                        f"Failed to publish plan switch to RabbitMQ for tenant {tenant_id}. "
                        "Auth server may not be updated."
                    )

            # Send email notifications for upgrades and renewals
            if switch_result.get("effective_immediately", True):
                try:
                    from ..services.email_publisher import email_publisher

                    # Determine if this is an upgrade or renewal
                    is_same_plan = (current_plan.id == new_plan.id) if current_plan else False
                    is_upgrade_plan = is_upgrade and not is_same_plan
                    is_renewal = is_same_plan  # Same plan = renewal after expiration

                    if is_upgrade_plan:
                        # Send upgrade notification
                        email_publisher.publish_plan_upgraded_email(
                            tenant_id=tenant_id,
                            to_email=claims.email,
                            to_name=claims.full_name or "Valued Customer",
                            old_plan_name=current_plan.name if current_plan else "Free",
                            new_plan_name=new_plan.name,
                            proration_amount=float(switch_result.get("prorated_amount", 0)),
                            currency=existing_subscription.currency or "NGN"
                        )
                        logger.info(f"Sent plan upgrade notification to {claims.email} for upgrade to {new_plan.name}")

                    elif is_renewal:
                        # Send renewal notification (user renewed same plan after expiration)
                        email_publisher.publish_subscription_renewed_email(
                            tenant_id=tenant_id,
                            to_email=claims.email,
                            to_name=claims.full_name or "Valued Customer",
                            plan_name=new_plan.name,
                            amount=float(new_cost),
                            currency=existing_subscription.currency or "NGN",
                            next_billing_date=existing_subscription.current_period_end
                        )
                        logger.info(f"Sent subscription renewal notification to {claims.email} for {new_plan.name}")

                except Exception as e:
                    # Don't fail the plan switch if email fails
                    logger.error(f"Failed to send plan switch notification email: {e}", exc_info=True)

            # Build response based on whether it's a scheduled downgrade or immediate change
            response = {
                "plan_switch": {
                    "tenant_id": tenant_id,
                    "subscription_id": existing_subscription.id,
                    "action": "downgrade_scheduled" if not switch_result.get("effective_immediately", True) else "plan_switched",
                    "previous_plan": {
                        "id": current_plan.id if current_plan else None,
                        "name": current_plan.name if current_plan else "Unknown"
                    },
                    "new_plan": {
                        "id": new_plan.id,
                        "name": new_plan.name,
                        "description": new_plan.description,
                        "document_limit": new_plan.document_limit,
                        "website_limit": new_plan.website_limit,
                        "daily_chat_limit": new_plan.daily_chat_limit,
                        "monthly_chat_limit": new_plan.monthly_chat_limit,
                        "features": new_plan.features
                    }
                },
                "billing_info": {
                    "billing_cycle": plan_switch.billing_cycle,
                    "old_cost": float(switch_result["old_amount"]),
                    "new_cost": float(switch_result["new_amount"]),
                    "prorated_amount": switch_result.get("prorated_amount"),
                    "is_upgrade": float(switch_result["new_amount"]) > float(switch_result["old_amount"]),
                    "is_downgrade": float(switch_result["new_amount"]) < float(switch_result["old_amount"])
                },
                "effective_immediately": switch_result.get("effective_immediately", True),
                "rabbitmq_notified": rabbitmq_success
            }

            # Add scheduled information if it's a downgrade
            if not switch_result.get("effective_immediately", True):
                response["scheduled_for"] = switch_result.get("scheduled_for")
                response["message"] = switch_result.get("message", f"Downgrade to {new_plan.name} scheduled")
            else:
                response["message"] = f"Successfully switched to {new_plan.name} plan"

            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to switch plan for tenant {tenant_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch plan: {str(e)}"
        )


@router.get("/plans/current", response_model=Dict[str, Any])
async def get_tenant_current_plan(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get authenticated tenant's current plan details"""

    tenant_id = claims.tenant_id

    try:
        from ..services.dependencies import get_full_tenant_details
        
        plan_service = PlanService(db)
        
        # Get tenant info
        target_tenant = await get_full_tenant_details(tenant_id, access_token=claims.access_token)
        if not target_tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get current plan
        current_plan = None
        if target_tenant["plan_id"]:
            current_plan = plan_service.get_plan_by_id(target_tenant["plan_id"])
        
        if not current_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No plan assigned to this tenant"
            )
        
        # Get available plans for comparison
        available_plans = plan_service.get_all_plans(active_only=True)
        
        return {
            "tenant_info": {
                "id": target_tenant["id"],
                "name": target_tenant.get("name"),
                "email": target_tenant.get("email"),
                "is_active": target_tenant.get("is_active")
            },
            "current_plan": {
                "id": current_plan.id,
                "name": current_plan.name,
                "description": current_plan.description,
                "document_limit": current_plan.document_limit,
                "website_limit": current_plan.website_limit,
                "daily_chat_limit": current_plan.daily_chat_limit,
                "monthly_chat_limit": current_plan.monthly_chat_limit,
                "monthly_plan_cost": str(current_plan.monthly_plan_cost),
                "yearly_plan_cost": str(current_plan.yearly_plan_cost),
                "features": current_plan.features,
                "is_active": current_plan.is_active
            },
            "available_plans": [
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": plan.description,
                    "document_limit": plan.document_limit,
                    "website_limit": plan.website_limit,
                    "daily_chat_limit": plan.daily_chat_limit,
                    "monthly_chat_limit": plan.monthly_chat_limit,
                    "monthly_plan_cost": str(plan.monthly_plan_cost),
                    "yearly_plan_cost": str(plan.yearly_plan_cost),
                    "features": plan.features,
                    "is_current": plan.id == current_plan.id
                }
                for plan in available_plans
            ],
            "can_switch_plans": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current plan: {str(e)}"
        )


