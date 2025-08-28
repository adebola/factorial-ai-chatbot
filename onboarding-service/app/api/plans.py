from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from decimal import Decimal
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..services.plan_service import PlanService
from ..services.dependencies import get_current_tenant, get_admin_tenant
from ..models.tenant import Tenant, Plan

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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List all plans (accessible to all authenticated users)"""
    
    try:
        plan_service = PlanService(db)
        plans = plan_service.get_all_plans(
            include_deleted=include_deleted and current_tenant.role.value == "admin",
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
                    "is_deleted": plan.is_deleted if current_tenant.role.value == "admin" else False,
                    "created_at": plan.created_at.isoformat(),
                    "updated_at": plan.updated_at.isoformat() if plan.updated_at else None
                }
                for plan in plans
            ],
            "total_plans": len(plans),
            "filters": {
                "include_deleted": include_deleted and current_tenant.role.value == "admin",
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get a specific plan by ID"""
    
    try:
        plan_service = PlanService(db)
        plan = plan_service.get_plan_by_id(
            plan_id, 
            include_deleted=current_tenant.role.value == "admin"
        )
        
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found"
            )
        
        # Get usage stats if admin
        usage_stats = None
        if current_tenant.role.value == "admin":
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
                "is_deleted": plan.is_deleted if current_tenant.role.value == "admin" else False,
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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
        
        return {
            "message": f"Plan '{plan.name}' deleted successfully",
            "plan_id": plan_id,
            "plan_name": plan.name,
            "deleted_by": {
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    admin_tenant: Tenant = Depends(get_admin_tenant),
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
                "admin_id": admin_tenant.id,
                "admin_username": admin_tenant.username
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Switch tenant's plan (only own plan unless admin)"""
    
    # Authorization check
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only switch your own plan unless you're an admin"
        )
    
    try:
        from ..services.tenant_service import TenantService
        
        plan_service = PlanService(db)
        tenant_service = TenantService(db)
        
        # Validate new plan exists and is active
        new_plan = plan_service.get_plan_by_id(plan_switch.new_plan_id)
        if not new_plan or not new_plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid plan or plan is not active"
            )
        
        # Get current tenant info
        target_tenant = tenant_service.get_tenant_by_id(tenant_id)
        if not target_tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get current plan for comparison
        current_plan = None
        if target_tenant.plan_id:
            current_plan = plan_service.get_plan_by_id(target_tenant.plan_id)
        
        # Update tenant's plan
        target_tenant.plan_id = new_plan.id
        db.commit()
        db.refresh(target_tenant)
        
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
        
        # Clear cache if using caching service
        try:
            from ..services.cache_service import CacheService
            cache_service = CacheService()
            cache_service.invalidate_tenant_cache(tenant_id=tenant_id, api_key=target_tenant.api_key)
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
                "user_id": current_tenant.id,
                "username": current_tenant.username,
                "is_admin": current_tenant.role.value == "admin"
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
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant's current plan details"""
    
    # Authorization check
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own plan unless you're an admin"
        )
    
    try:
        from ..services.tenant_service import TenantService
        
        plan_service = PlanService(db)
        tenant_service = TenantService(db)
        
        # Get tenant info
        target_tenant = tenant_service.get_tenant_by_id(tenant_id)
        if not target_tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get current plan
        current_plan = None
        if target_tenant.plan_id:
            current_plan = plan_service.get_plan_by_id(target_tenant.plan_id)
        
        if not current_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No plan assigned to this tenant"
            )
        
        # Get available plans for comparison
        available_plans = plan_service.get_all_plans(active_only=True)
        
        return {
            "tenant_info": {
                "id": target_tenant.id,
                "name": target_tenant.name,
                "email": target_tenant.email,
                "is_active": target_tenant.is_active
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