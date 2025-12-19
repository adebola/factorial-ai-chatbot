import io
import os
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from typing import Dict, Any

from ..core.database import get_db
from ..services.settings_service import SettingsService
from ..services.dependencies import validate_token, TokenClaims, get_tenant_settings
from ..services.rabbitmq_service import rabbitmq_service
from ..core.logging_config import (get_logger)

router = APIRouter()
logger = get_logger("tenant_logo")

@router.post("/settings-logo/upload")
async def upload_logo(
    file: UploadFile = File(...),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Upload company logo for OAuth2 proxy (requires Bearer token authentication)"""
    
    # For now, allow any authenticated user to upload logos for any tenant
    # In a stricter implementation; you might validate tenant access
    tenant_id = claims.tenant_id
    
    try:
        settings_service = SettingsService(db)
        
        # Upload logo and get the permanent public URL (using public endpoint, not presigned URL)
        public_logo_url = settings_service.upload_company_logo(tenant_id, file)

        logger.info(
            f"Uploaded company logo for tenant {tenant_id}",
            extra={
                "tenant_id": tenant_id,
                "logo_url": public_logo_url,
                "filename": file.filename
            }
        )

        # Publish logo uploaded event to RabbitMQ with permanent URL
        try:
            rabbitmq_service.publish_logo_uploaded(
                tenant_id=tenant_id,
                logo_url=public_logo_url
            )
            logger.info(
                f"Published logo uploaded event to OAuth2 server",
                extra={
                    "tenant_id": tenant_id,
                    "logo_url": public_logo_url
                }
            )
        except Exception as e:
            logger.warning(f"Failed to publish logo uploaded event: {e}")

        return {
            "message": "Company logo uploaded successfully",
            "logo_url": public_logo_url,
            "filename": file.filename,
            "tenant_id": tenant_id,
            "uploaded_by": claims.tenant_id,
            "expires": False,
            "endpoint": f"/api/v1/settings-logo/{tenant_id}"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload company logo: {str(e)}"
        )


@router.get("/settings-logo")
async def get_logo_info(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get company logo information for OAuth2 proxy (requires Bearer token authentication)"""

    tenant_id = claims.tenant_id

    try:

        settings = get_tenant_settings(tenant_id, claims.access_token)

        if not settings or not settings["logo_url"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No company logo found"
            )
        
        return {
            "logo_url": settings['logo_url'],
            "tenant_id": tenant_id,
            # "uploaded_at": settings.updated_at.isoformat() if settings.updated_at else settings.created_at.isoformat(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve company logo information: {str(e)}"
        )


@router.delete("/settings-logo")
async def delete_logo(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Delete company logo for OAuth2 proxy (requires Bearer token authentication)"""

    tenant_id = claims.tenant_id

    try:
        settings_service = SettingsService(db)
        success = settings_service.remove_company_logo(tenant_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No company logo found to remove"
            )
        
        # Publish logo deleted event to RabbitMQ
        try:
            rabbitmq_service.publish_logo_deleted(tenant_id=tenant_id)
        except Exception as e:
            logger.warning(f"Failed to publish logo deleted event: {e}")
        
        return {
            "message": "Company logo removed successfully",
            "tenant_id": tenant_id,
            "deleted_by": claims.tenant_id
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
            detail=f"Failed to remove company logo: {str(e)}"
        )


@router.get("/settings-logo/download")
async def download_logo(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> StreamingResponse:
    """Download the company logo file for OAuth2 proxy (requires Bearer token authentication)"""

    tenant_id = claims.tenant_id

    try:
        settings_service = SettingsService(db)
        settings = settings_service.get_tenant_settings(tenant_id)

        if not settings or not settings.company_logo_object_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Logo not found"
            )
        
        # Download logo from storage
        logo_data = settings_service.storage_service.download_file(settings.company_logo_object_name)
        
        # Determine content type based on file extension
        _, ext = os.path.splitext(settings.company_logo_object_name)
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg', 
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        content_type = content_type_map.get(ext.lower(), 'application/octet-stream')
        
        # Create filename from original logo object name
        filename = os.path.basename(settings.company_logo_object_name) or f"logo-{tenant_id}{ext}"
        
        return StreamingResponse(
            io.BytesIO(logo_data),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download logo file: {str(e)}"
        )


def _serve_tenant_logo(tenant_id: str, db: Session) -> Response:
    """Helper function to serve tenant logo from MinIO storage"""
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


@router.get("/settings-logo/{tenant_id}")
async def get_public_logo(
    tenant_id: str,
    db: Session = Depends(get_db)
) -> Response:
    """Public endpoint to serve logo files (no authentication required)"""

    try:
        return _serve_tenant_logo(tenant_id, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to serve logo file: {str(e)}"
        )


@router.get("/public/logos/{tenant_id}")
async def get_public_logo_alias(
    tenant_id: str,
    db: Session = Depends(get_db)
) -> Response:
    """
    Public endpoint to serve logo files - alias for auth server proxy compatibility.
    This endpoint matches the path expected by the auth server's LogoProxyController.
    No authentication required.
    """

    try:
        return _serve_tenant_logo(tenant_id, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to serve logo file: {str(e)}"
        )