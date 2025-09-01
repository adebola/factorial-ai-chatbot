import uuid

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, Enum, ForeignKey, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TenantRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class Plan(Base):
    __tablename__ = "plans"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    # Limits
    document_limit = Column(Integer, nullable=False, default=10)
    website_limit = Column(Integer, nullable=False, default=1) 
    daily_chat_limit = Column(Integer, nullable=False, default=50)
    monthly_chat_limit = Column(Integer, nullable=False, default=1500)
    
    # Pricing
    monthly_plan_cost = Column(Numeric(10, 2), nullable=False, default=0.00)
    yearly_plan_cost = Column(Numeric(10, 2), nullable=False, default=0.00)
    
    # Features
    features = Column(JSON, default={})  # Additional features as JSON
    
    # Soft deletion
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    tenants = relationship("Tenant", back_populates="plan")


class Tenant(Base):
    __tablename__ = "tenant"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, index=True)
    website_url = Column(String(500))
    api_key = Column(String(255), unique=True, index=True)
    
    # Authentication fields
    username = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True, index=True)
    role = Column(Enum(TenantRole), default=TenantRole.USER, nullable=False)
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Plan relationship
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=True, index=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Configuration for this tenant
    config = Column(JSON, default={})
    
    # Relationships
    plan = relationship("Plan", back_populates="tenants")
    settings = relationship("TenantSettings", back_populates="tenant", uselist=False)


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # MinIO path
    file_size = Column(Integer)
    mime_type = Column(String(100))
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))


class WebsiteIngestion(Base):
    __tablename__ = "website_ingestions"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    base_url = Column(String(500), nullable=False)
    status = Column(Enum(IngestionStatus), default=IngestionStatus.PENDING)
    pages_discovered = Column(Integer, default=0)
    pages_processed = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WebsitePage(Base):
    __tablename__ = "website_pages"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    ingestion_id = Column(String(36), nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    title = Column(String(500))
    content_hash = Column(String(64))  # SHA256 of content
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    error_message = Column(Text)
    scraped_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())