from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from ..core.database import get_db
from ..services.tenant_service import TenantService, TenantCreate
from ..services.widget_service import WidgetService
from ..services.cache_service import CacheService
from ..services.dependencies import get_admin_tenant, get_current_tenant
from ..models.tenant import Tenant

router = APIRouter()


@router.post("/tenants/", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Create a new tenant"""
    
    tenant_service = TenantService(db)
    
    try:
        tenant = tenant_service.create_tenant(tenant_data)
        
        # Generate widget files for the new tenant
        widget_service = WidgetService(db)
        widget_files = widget_service.generate_widget_files(tenant)
        
        return {
            "id": tenant.id,
            "name": tenant.name,
            "domain": tenant.domain,
            "username": tenant.username,
            "email": tenant.email,
            "role": tenant.role,
            "api_key": tenant.api_key,
            "website_url": tenant.website_url,
            "plan_id": tenant.plan_id,
            "is_active": tenant.is_active,
            "created_at": tenant.created_at.isoformat(),
            "chat_widget": {
                "status": "generated",
                "files_available": list(widget_files.keys()),
                "download_urls": {
                    "javascript": f"/api/v1/tenants/{tenant.id}/widget/chat-widget.js",
                    "css": f"/api/v1/tenants/{tenant.id}/widget/chat-widget.css",
                    "demo": f"/api/v1/tenants/{tenant.id}/widget/chat-widget.html",
                    "integration_guide": f"/api/v1/tenants/{tenant.id}/widget/integration-guide.html",
                    "download_all": f"/api/v1/tenants/{tenant.id}/widget/download-all",
                    "preview": f"/api/v1/tenants/{tenant.id}/widget/preview"
                },
                "integration_snippet": f'<script src="https://your-domain.com/path/to/chat-widget.js"></script>'
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
            detail="Failed to create tenant"
        )


@router.get("/tenants/{tenant_id}/public")
async def get_tenant_public_info(
    tenant_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get public tenant information (no authentication required, limited data)"""
    
    cache_service = CacheService()
    
    # Check cache first
    cached_tenant = cache_service.get_cached_tenant('id', tenant_id)
    if cached_tenant:
        return cached_tenant
    
    # Fetch from database
    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive"
        )
    
    tenant_data = {
        "id": tenant.id,
        "name": tenant.name,
        "domain": tenant.domain,
        "website_url": tenant.website_url,
        "api_key": tenant.api_key,  # Include API key for caching
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
        "widget_available": True
    }
    
    # Cache the result
    cache_service.cache_tenant(tenant_data)
    
    return tenant_data



@router.get("/tenants/lookup")
async def lookup_tenant_by_access_token(
    access_token: str = Query(..., description="JWT access token"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Lookup tenant by access token (public endpoint for chat service)"""
    
    from ..services.auth import AuthService
    cache_service = CacheService()
    
    # Verify and decode the JWT token
    payload = AuthService.verify_token(access_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token"
        )
    
    # Extract tenant_id from token payload
    tenant_id = payload.get("sub") or payload.get("user_id") or payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing tenant identifier"
        )
    
    # Check cache first using tenant_id
    cached_tenant = cache_service.get_cached_tenant('id', tenant_id)
    if cached_tenant:
        return cached_tenant
    
    # Fetch from database
    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive"
        )
    
    tenant_data = {
        "id": tenant.id,
        "name": tenant.name,
        "domain": tenant.domain,
        "website_url": tenant.website_url,
        "api_key": tenant.api_key,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
        "widget_available": True
    }
    
    # Cache the result by both id and api_key for flexibility
    cache_service.cache_tenant(tenant_data)
    
    return tenant_data


@router.get("/tenants/lookup-by-api-key")
async def lookup_tenant_by_api_key(
    api_key: str = Query(..., description="Tenant API key"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Lookup tenant by API key (public endpoint for chat widget)"""
    
    cache_service = CacheService()
    
    # Check cache first
    cached_tenant = cache_service.get_cached_tenant('api_key', api_key)
    if cached_tenant:
        return cached_tenant
    
    # Fetch from database
    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_api_key(api_key)
    
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive"
        )
    
    tenant_data = {
        "id": tenant.id,
        "name": tenant.name,
        "domain": tenant.domain,
        "website_url": tenant.website_url,
        "api_key": tenant.api_key,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
        "widget_available": True
    }
    
    # Cache the result
    cache_service.cache_tenant(tenant_data)
    
    return tenant_data


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant by ID (requires authentication)"""
    
    # Users can only access their own tenant information unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own tenant information."
        )
    
    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    return {
        "id": tenant.id,
        "name": tenant.name,
        "domain": tenant.domain,
        "username": tenant.username,
        "email": tenant.email,
        "role": tenant.role.value,
        "website_url": tenant.website_url,
        "plan_id": tenant.plan_id,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat(),
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
        "config": tenant.config
    }


@router.put("/tenants/{tenant_id}/config")
async def update_tenant_config(
    tenant_id: str,
    config: Dict[str, Any],
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Update tenant configuration"""
    
    tenant_service = TenantService(db)
    
    try:
        tenant = tenant_service.update_tenant_config(tenant_id, config)
        
        return {
            "id": tenant.id,
            "config": tenant.config,
            "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/tenants/")
async def list_all_tenants(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    admin_tenant: Tenant = Depends(get_admin_tenant)
) -> Dict[str, Any]:
    """List all tenants (admin only)"""
    
    tenant_service = TenantService(db)
    tenants = tenant_service.get_all_tenants(skip=skip, limit=limit)
    
    tenants_data = []
    for tenant in tenants:
        tenants_data.append({
            "id": tenant.id,
            "name": tenant.name,
            "domain": tenant.domain,
            "username": tenant.username,
            "email": tenant.email,
            "role": tenant.role,
            "website_url": tenant.website_url,
            "is_active": tenant.is_active,
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None
        })
    
    return {
        "tenants": tenants_data,
        "total": len(tenants_data),
        "skip": skip,
        "limit": limit
    }
