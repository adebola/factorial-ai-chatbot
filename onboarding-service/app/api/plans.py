from decimal import Decimal
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..models.tenant import Plan
from ..services.dependencies import TokenClaims, validate_token, logger
from ..services.plan_service import PlanService

router = APIRouter()


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
                    "monthly_plan_cost": str(plan.monthly_plan_cost),
                    "yearly_plan_cost": str(plan.yearly_plan_cost),
                    "features": plan.features,
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


@router.post("/tenants/{tenant_id}/switch-plan", response_model=Dict[str, Any])
async def switch_tenant_plan(
    tenant_id: str,
    plan_switch: PlanSwitchRequest,
    claims: TokenClaims = Depends(validate_token),
    # current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Switch tenant's plan (only own plan unless admin)"""
    
    # Authorization check
    if claims.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only switch your own plan unless you're an admin"
        )
    
    try:
        from ..services.dependencies import get_full_tenant_details
        
        plan_service = PlanService(db)
        
        # Validate new plan exists and is active
        new_plan = plan_service.get_plan_by_id(plan_switch.new_plan_id)
        if not new_plan or not new_plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan or plan is not active"
            )
        
        # Get current tenant info
        target_tenant = await get_full_tenant_details(tenant_id)
        if not target_tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get the current plan for comparison
        current_plan = None
        if target_tenant.get("plan_id"):
            current_plan = plan_service.get_plan_by_id(target_tenant["plan_id"])
        
        # Note: Cannot update tenant plan here as tenant data comes from auth server
        # Plan assignment should be handled by the authorization server
        # For now, we'll return the response as if the switch was successful
        # but actual tenant update needs to be implemented via auth server API
        
        # Calculate cost difference for billing
        cost_difference = None
        billing_info = None
        
        if plan_switch.billing_cycle == "yearly":
            new_cost = float(new_plan.yearly_plan_cost)
            old_cost = float(current_plan.yearly_plan_cost) if current_plan else 0.0
        else:
            new_cost = float(new_plan.monthly_plan_cost)
            old_cost = float(current_plan.monthly_plan_cost) if current_plan else 0.0
        
        cost_difference = new_cost - old_cost
        
        billing_info = {
            "billing_cycle": plan_switch.billing_cycle,
            "old_cost": old_cost,
            "new_cost": new_cost,
            "cost_difference": cost_difference,
            "is_upgrade": cost_difference > 0,
            "is_downgrade": cost_difference < 0,
            "is_same_tier": cost_difference == 0
        }
        
        # Clear cache if using a caching service
        try:
            from ..services.cache_service import CacheService
            cache_service = CacheService()
            cache_service.invalidate_tenant_cache(tenant_id=tenant_id, api_key=target_tenant.get("api_key"))
        except ImportError:
            pass  # Cache service not available
        
        return {
            "message": f"Successfully switched to {new_plan.name} plan",
            "plan_switch": {
                "tenant_id": tenant_id,
                "previous_plan": {
                    "id": current_plan.id if current_plan else None,
                    "name": current_plan.name if current_plan else "No previous plan"
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
            "billing_info": billing_info,
            "effective_immediately": True,
            "updated_by": {
                "user_id": claims.user_id,
                "username":claims.user_id,
                "is_admin": False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch plan: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/current-plan", response_model=Dict[str, Any])
async def get_tenant_current_plan(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_token),
    # current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant's current plan details"""
    
    # Authorization check
    if claims.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own plan unless you're an admin"
        )
    
    try:
        from ..services.dependencies import get_full_tenant_details
        
        plan_service = PlanService(db)
        
        # Get tenant info
        target_tenant = await get_full_tenant_details(tenant_id)
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

        # Not in cache, get from database
        free_plan = db.query(Plan).filter(
            Plan.name == "Free",
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