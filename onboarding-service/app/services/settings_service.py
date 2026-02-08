"""
DEPRECATED: This settings service is deprecated and will be removed in a future version.
Tenant settings functionality has been migrated to the OAuth2 Authorization Server.

Use the new OAuth2 server API endpoints instead:
- TenantSettingsService (OAuth2 server)
- TenantSettingsController (OAuth2 server)
- LogoProxyController (OAuth2 server)

This service is kept for backward compatibility during migration but should not be used for new integrations.
"""

import os
import re
from typing import Optional, Dict, Any
from fastapi import UploadFile
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from .storage_service import StorageService


class SettingsUpdate(BaseModel):
    """Pydantic model for updating tenant settings"""
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    hover_text: Optional[str] = None
    welcome_message: Optional[str] = None
    chat_window_title: Optional[str] = None
    additional_settings: Optional[Dict[str, Any]] = None

    @validator('primary_color', 'secondary_color')
    def validate_hex_color(cls, v):
        """Validate hex color format"""
        if v is not None:
            if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
                raise ValueError('Color must be a valid hex color code (e.g., #FF5733)')
        return v

    @validator('hover_text')
    def validate_hover_text(cls, v):
        """Validate hover text length"""
        if v is not None and len(v) > 255:
            raise ValueError('Hover text must be 255 characters or less')
        return v

    @validator('chat_window_title')
    def validate_chat_window_title(cls, v):
        """Validate chat window title length"""
        if v is not None and len(v) > 100:
            raise ValueError('Chat window title must be 100 characters or less')
        return v

    @validator('welcome_message')
    def validate_welcome_message(cls, v):
        """Validate welcome message length"""
        if v is not None and len(v) > 2000:
            raise ValueError('Welcome message must be 2000 characters or less')
        return v


class SettingsResponse(BaseModel):
    """Pydantic model for settings response"""
    id: str
    tenant_id: str
    primary_color: Optional[str]
    secondary_color: Optional[str]
    company_logo_url: Optional[str]
    company_logo_object_name: Optional[str]
    hover_text: Optional[str]
    welcome_message: Optional[str]
    chat_window_title: Optional[str]
    additional_settings: Dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class SettingsService:
    """Service for managing tenant settings"""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_service = StorageService()
        self.allowed_logo_types = {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/svg+xml",
            "image/webp"
        }
        self.max_logo_size = 5 * 1024 * 1024  # 5MB

    def _construct_public_logo_url(self, tenant_id: str) -> str:
        """
        Construct public logo URL using the service's public endpoint.

        This URL is permanent (no expiration) and uses the external API hostname
        instead of internal MinIO hostname.

        Args:
            tenant_id: Tenant ID

        Returns:
            Public logo URL like: http://api.domain.com/api/v1/settings-logo/{tenant_id}
        """
        import logging
        logger = logging.getLogger(__name__)

        # Get base URL from environment
        backend_url = os.environ.get("BACKEND_URL")

        if not backend_url:
            logger.warning(
                "BACKEND_URL not set in environment, using default localhost. "
                "This may cause issues in production!"
            )
            backend_url = "http://localhost:8001"

        # Remove trailing slash if present
        backend_url = backend_url.rstrip('/')

        # Construct public endpoint URL
        public_logo_url = f"{backend_url}/api/v1/settings-logo/{tenant_id}"

        logger.debug(
            f"Constructed public logo URL",
            extra={
                "tenant_id": tenant_id,
                "url": public_logo_url
            }
        )

        return public_logo_url

    def validate_logo_file(self, file: UploadFile) -> None:
        """Validate logo file type and size"""
        # Check content type
        if file.content_type not in self.allowed_logo_types:
            raise ValueError(
                f"Unsupported logo file type: {file.content_type}. "
                f"Allowed types: {', '.join(self.allowed_logo_types)}"
            )
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if file_size > self.max_logo_size:
            raise ValueError(
                f"Logo file too large: {file_size} bytes. "
                f"Maximum size: {self.max_logo_size} bytes ({self.max_logo_size // 1024 // 1024}MB)"
            )

    def upload_company_logo(self, tenant_id: str, file: UploadFile) -> str:
        """Upload company logo and return the object name"""
        # Validate file
        self.validate_logo_file(file)
        
        # Generate filename for logo
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
        logo_filename = f"logo{file_extension}"
        
        try:
            # Delete the existing logo if it exists (try common extensions)
            logo_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.webp']
            for ext in logo_extensions:
                try:
                    self.storage_service.delete_file(f"tenant_{tenant_id}/settings/logo{ext}")
                except:
                    continue  # Ignore if the file doesn't exist
            
            # Delete existing logos first (try common extensions)
            logo_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.webp']
            for ext in logo_extensions:
                try:
                    old_object_name = f"tenant_{tenant_id}/logos/logo{ext}"
                    self.storage_service.delete_file(old_object_name)
                except:
                    continue  # Ignore if file doesn't exist
            
            # Upload new logo to storage using StorageService method
            object_name, temporary_url = self.storage_service.upload_logo_file(
                tenant_id=tenant_id,
                file_data=file.file,
                filename=file.filename,
                content_type=file.content_type
            )

            # Construct permanent public URL (using public endpoint, not presigned URL)
            public_logo_url = self._construct_public_logo_url(tenant_id)

            # Send a message to OAuth2 server to update tenant settings logo URL
            try:
                from .rabbitmq_service import rabbitmq_service
                import asyncio
                asyncio.ensure_future(rabbitmq_service.publish_logo_uploaded(
                    tenant_id=tenant_id,
                    logo_url=public_logo_url
                ))
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Published logo uploaded event to OAuth2 server",
                    extra={
                        "tenant_id": tenant_id,
                        "logo_url": public_logo_url,
                        "object_name": object_name
                    }
                )
            except Exception as e:
                # Log error but don't fail the logo upload
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to publish logo update message: {e}")

            return public_logo_url  # Return the permanent public URL
            
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Failed to upload logo: {str(e)}")

    def remove_company_logo(self, tenant_id: str) -> bool:
        """Remove company logo"""
        try:
            # Delete logo files from storage (try all common extensions)
            logo_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.webp']
            deleted_any = False
            
            for ext in logo_extensions:
                try:
                    object_name = f"tenant_{tenant_id}/logos/logo{ext}"
                    if self.storage_service.delete_file(object_name):
                        deleted_any = True
                except:
                    continue  # Ignore if the file doesn't exist
            
            # Send a message to the OAuth2 server to clear the logo URL
            try:
                from .rabbitmq_service import rabbitmq_service
                rabbitmq_service.publish_logo_deleted(
                    tenant_id=tenant_id
                )
            except Exception as e:
                # Log error but don't fail the logo removal
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to publish logo removal message: {e}")
            
            return deleted_any
            
        except Exception as e:
            raise ValueError(f"Failed to remove logo: {str(e)}")