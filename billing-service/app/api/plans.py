from decimal import Decimal
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
    from datetime import timedelta
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

            # Create subscription with custom trial end
            subscription = subscription_service.create_subscription(
                tenant_id=tenant_id,
                plan_id=basic_plan.id,
                billing_cycle=billing_cycle,
                start_trial=False,  # We're using custom_trial_end instead
                custom_trial_end=trial_end_date,
                metadata={
                    "created_via": "switch_tenant_plan",
                    "user_id": claims.user_id,
                    "initial_plan": True
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
                    "status": subscription.status.value,
                    "billing_cycle": subscription.billing_cycle.value,
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
                if existing_subscription.status in [
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING
                ]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"You are already subscribed to the {new_plan.name} plan. "
                               f"Your subscription is currently {existing_subscription.status.value}."
                    )

            # Switch subscription plan
            switch_result = subscription_service.switch_subscription_plan(
                subscription_id=existing_subscription.id,
                new_plan_id=new_plan.id,
                billing_cycle=billing_cycle,
                prorate=True
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


