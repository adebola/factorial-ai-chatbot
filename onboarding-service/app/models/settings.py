import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .tenant import Base


class TenantSettings(Base):
    """Tenant-specific settings for chat widget and branding customization"""
    __tablename__ = "tenant_settings"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenant.id"), nullable=False, unique=True, index=True)
    
    # Company branding
    primary_color = Column(String(7), nullable=True)  # Hex color code #RRGGBB
    secondary_color = Column(String(7), nullable=True)  # Hex color code #RRGGBB
    company_logo_url = Column(String(1000), nullable=True)  # Public URL for frontend/widget use
    company_logo_object_name = Column(String(500), nullable=True)  # Internal storage path
    
    # Chat widget text customization
    hover_text = Column(String(255), nullable=True, default="Chat with us!")
    welcome_message = Column(Text, nullable=True, default="Hello! How can I help you today?")
    chat_window_title = Column(String(100), nullable=True, default="Chat Support")
    
    # Future extensibility
    additional_settings = Column(JSON, default={})  # For future settings without schema changes
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship back to tenant
    tenant = relationship("Tenant", back_populates="settings")


def get_default_settings() -> dict:
    """
    Get default settings values for new tenants
    """
    return {
        "primary_color": "#5D3EC1",  # Default factorial purple
        "secondary_color": "#C15D3E",  # Default factorial orange
        "hover_text": "Chat with us!",
        "welcome_message": "Hello! How can I help you today?",
        "chat_window_title": "Chat Support",
        "additional_settings": {}
    }