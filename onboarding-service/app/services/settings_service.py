from sqlalchemy.orm import Session
from typing import Optional, BinaryIO, Dict, Any
import re
import os
from pydantic import BaseModel, validator
from fastapi import UploadFile

from ..models.settings import TenantSettings, get_default_settings
from ..models.tenant import Tenant
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

    def get_tenant_settings(self, tenant_id: str) -> Optional[TenantSettings]:
        """Get tenant settings by tenant ID"""
        return self.db.query(TenantSettings).filter(
            TenantSettings.tenant_id == tenant_id,
            TenantSettings.is_active == True
        ).first()

    def get_or_create_tenant_settings(self, tenant_id: str) -> TenantSettings:
        """Get existing settings or create with defaults if they don't exist"""
        settings = self.get_tenant_settings(tenant_id)
        
        if not settings:
            # Verify tenant exists
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")
            
            # Create default settings
            settings = self.create_default_settings(tenant_id)
        
        return settings

    def create_default_settings(self, tenant_id: str) -> TenantSettings:
        """Create default settings for a tenant"""
        defaults = get_default_settings()
        
        settings = TenantSettings(
            tenant_id=tenant_id,
            primary_color=defaults["primary_color"],
            secondary_color=defaults["secondary_color"],
            hover_text=defaults["hover_text"],
            welcome_message=defaults["welcome_message"],
            chat_window_title=defaults["chat_window_title"],
            additional_settings=defaults["additional_settings"]
        )
        
        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        
        return settings

    def update_tenant_settings(self, tenant_id: str, settings_data: SettingsUpdate) -> TenantSettings:
        """Update tenant settings"""
        settings = self.get_or_create_tenant_settings(tenant_id)
        
        # Update only provided fields
        update_data = settings_data.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            if hasattr(settings, field):
                setattr(settings, field, value)
        
        self.db.commit()
        self.db.refresh(settings)
        
        return settings

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
            
            # Upload logo using the dedicated logo upload method
            logo_object_name, public_url = self.storage_service.upload_logo_file(
                tenant_id=tenant_id,
                file_data=file.file,
                filename=logo_filename,
                content_type=file.content_type
            )
            
            # Update settings with both object name and public URL
            settings = self.get_or_create_tenant_settings(tenant_id)
            settings.company_logo_object_name = logo_object_name  # Store for internal use
            settings.company_logo_url = public_url  # Store the public URL for frontend/widget use
            
            self.db.commit()
            self.db.refresh(settings)
            
            return public_url  # Return the public URL instead of the object name
            
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Failed to upload logo: {str(e)}")

    def remove_company_logo(self, tenant_id: str) -> bool:
        """Remove company logo"""
        settings = self.get_tenant_settings(tenant_id)
        if not settings or not settings.company_logo_url:
            return False
        
        try:
            # Delete the actual logo file using the stored object name
            if settings.company_logo_object_name:
                self.storage_service.delete_file(settings.company_logo_object_name)
            
            # Remove logo from settings
            settings.company_logo_url = None
            settings.company_logo_object_name = None
            
            self.db.commit()
            self.db.refresh(settings)
            
            return True
            
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Failed to remove logo: {str(e)}")

    def delete_tenant_settings(self, tenant_id: str) -> bool:
        """Soft delete tenant settings"""
        settings = self.get_tenant_settings(tenant_id)
        if not settings:
            return False
        
        settings.is_active = False
        self.db.commit()
        
        return True

    def to_dict(self, settings: TenantSettings) -> SettingsResponse:
        """Convert TenantSettings to response format"""
        return SettingsResponse(
            id=settings.id,
            tenant_id=settings.tenant_id,
            primary_color=settings.primary_color,
            secondary_color=settings.secondary_color,
            company_logo_url=settings.company_logo_url,
            company_logo_object_name=settings.company_logo_object_name,
            hover_text=settings.hover_text,
            welcome_message=settings.welcome_message,
            chat_window_title=settings.chat_window_title,
            additional_settings=settings.additional_settings or {},
            is_active=settings.is_active,
            created_at=settings.created_at.isoformat(),
            updated_at=settings.updated_at.isoformat() if settings.updated_at else None
        )