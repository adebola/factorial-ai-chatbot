from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Dict, Any

from ..core.database import get_db
from ..services.settings_service import SettingsService, SettingsUpdate, SettingsResponse
from ..services.dependencies import get_current_tenant
from ..models.tenant import Tenant

router = APIRouter()


@router.get("/tenants/{tenant_id}/settings")
async def get_tenant_settings(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> SettingsResponse:
    """Get tenant settings (requires authentication)"""
    
    # Users can only access their own tenant settings unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own tenant settings."
        )
    
    try:
        settings_service = SettingsService(db)
        settings = settings_service.get_or_create_tenant_settings(tenant_id)
        
        return settings_service.to_dict(settings)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tenant settings"
        )


@router.put("/tenants/{tenant_id}/settings")
async def update_tenant_settings(
    tenant_id: str,
    settings_data: SettingsUpdate,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> SettingsResponse:
    """Update tenant settings (requires authentication)"""
    
    # Users can only update their own tenant settings unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only update your own tenant settings."
        )
    
    try:
        settings_service = SettingsService(db)
        settings = settings_service.update_tenant_settings(tenant_id, settings_data)
        
        return settings_service.to_dict(settings)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tenant settings"
        )


@router.post("/tenants/{tenant_id}/settings/logo")
async def upload_company_logo(
    tenant_id: str,
    file: UploadFile = File(...),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Upload company logo (requires authentication)"""
    
    # Users can only upload to their own tenant unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only upload to your own tenant."
        )
    
    try:
        settings_service = SettingsService(db)
        logo_object_name = settings_service.upload_company_logo(tenant_id, file)
        
        return {
            "message": "Company logo uploaded successfully",
            "logo_object_name": logo_object_name,
            "filename": file.filename,
            "tenant_id": tenant_id
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload company logo"
        )


@router.delete("/tenants/{tenant_id}/settings/logo")
async def remove_company_logo(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Remove company logo (requires authentication)"""
    
    # Users can only remove from their own tenant unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only modify your own tenant."
        )
    
    try:
        settings_service = SettingsService(db)
        success = settings_service.remove_company_logo(tenant_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No company logo found to remove"
            )
        
        return {
            "message": "Company logo removed successfully",
            "tenant_id": tenant_id
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove company logo"
        )


@router.get("/tenants/{tenant_id}/settings/logo")
async def get_company_logo(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get company logo information (requires authentication)"""
    
    # Users can only access their own tenant logo unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only access your own tenant information."
        )
    
    try:
        settings_service = SettingsService(db)
        settings = settings_service.get_tenant_settings(tenant_id)
        
        if not settings or not settings.company_logo_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No company logo found"
            )
        
        return {
            "logo_url": settings.company_logo_url,
            "logo_object_name": settings.company_logo_object_name,
            "tenant_id": tenant_id,
            "uploaded_at": settings.updated_at.isoformat() if settings.updated_at else settings.created_at.isoformat()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve company logo information"
        )


@router.get("/public/logos/{tenant_id}")
async def get_public_logo(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """Public endpoint to serve logo files (no authentication required)"""
    from fastapi.responses import Response
    
    try:
        settings_service = SettingsService(db)
        settings = settings_service.get_tenant_settings(tenant_id)
        
        if not settings or not settings.company_logo_object_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Logo not found"
            )
        
        # Download logo from storage and serve it
        logo_data = settings_service.storage_service.download_file(settings.company_logo_object_name)
        
        # Determine content type based on file extension
        import os
        _, ext = os.path.splitext(settings.company_logo_object_name)
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg', 
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        content_type = content_type_map.get(ext.lower(), 'image/jpeg')
        
        return Response(
            content=logo_data,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "ETag": f'"{tenant_id}-logo"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to serve logo file"
        )


@router.delete("/tenants/{tenant_id}/settings")
async def delete_tenant_settings(
    tenant_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Soft delete tenant settings (admin only or own tenant)"""
    
    # Users can only delete their own tenant settings unless they're admin
    if current_tenant.id != tenant_id and current_tenant.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only delete your own tenant settings."
        )
    
    try:
        settings_service = SettingsService(db)
        success = settings_service.delete_tenant_settings(tenant_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant settings not found"
            )
        
        return {
            "message": "Tenant settings deleted successfully",
            "tenant_id": tenant_id
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete tenant settings"
        )