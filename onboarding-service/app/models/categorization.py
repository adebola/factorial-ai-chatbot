"""
Document categorization and tagging models.
"""
import uuid
from typing import List, Optional, Dict
from dataclasses import dataclass

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from .tenant import Base  # Use the same Base as other models


@dataclass
class DocumentClassification:
    """Container for document classification results."""
    categories: List[Dict[str, float]]  # [{"name": "Legal", "confidence": 0.95}]
    tags: List[Dict[str, float]]        # [{"name": "contract", "confidence": 0.89}]
    content_type: str                   # "contract", "invoice", "report", etc.
    language: str                       # "en", "es", "fr"
    sentiment: str                      # "neutral", "positive", "negative"
    key_entities: List[str]             # ["Company ABC", "John Doe", "$10,000"]


class DocumentCategory(Base):
    """Hierarchical categories for organizing documents."""
    __tablename__ = "document_categories"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    parent_category_id = Column(String(36), ForeignKey('document_categories.id'), nullable=True)
    color = Column(String(7), nullable=True)  # Hex color for UI
    icon = Column(String(50), nullable=True)  # Icon name for UI
    is_system_category = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent_category = relationship(
        "DocumentCategory",
        remote_side=[id],
        backref="subcategories"
    )

    document_assignments = relationship(
        "DocumentCategoryAssignment",
        back_populates="category",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', 'parent_category_id',
                        name='uq_document_categories_tenant_name_parent'),
    )

    def __repr__(self):
        return f"<DocumentCategory(id='{self.id}', name='{self.name}', tenant='{self.tenant_id}')>"


class DocumentTag(Base):
    """Flexible tags for document organization."""
    __tablename__ = "document_tags"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    tag_type = Column(String(50), default='custom', nullable=False)  # 'auto', 'custom', 'system'
    usage_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    document_assignments = relationship(
        "DocumentTagAssignment",
        back_populates="tag",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_document_tags_tenant_name'),
    )

    def __repr__(self):
        return f"<DocumentTag(id='{self.id}', name='{self.name}', type='{self.tag_type}')>"


class DocumentCategoryAssignment(Base):
    """Many-to-many relationship between documents and categories."""
    __tablename__ = "document_category_assignments"

    document_id = Column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    category_id = Column(String(36), ForeignKey('document_categories.id', ondelete='CASCADE'), primary_key=True)
    confidence_score = Column(Float, default=1.0, nullable=False)
    assigned_by = Column(String(20), default='user', nullable=False)  # 'user', 'ai', 'rule'
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    category = relationship("DocumentCategory", back_populates="document_assignments")
    document = relationship("Document", back_populates="category_assignments")

    def __repr__(self):
        return f"<DocumentCategoryAssignment(document='{self.document_id}', category='{self.category_id}', confidence={self.confidence_score})>"


class DocumentTagAssignment(Base):
    """Many-to-many relationship between documents and tags."""
    __tablename__ = "document_tag_assignments"

    document_id = Column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    tag_id = Column(String(36), ForeignKey('document_tags.id', ondelete='CASCADE'), primary_key=True)
    confidence_score = Column(Float, default=1.0, nullable=False)
    assigned_by = Column(String(20), default='user', nullable=False)  # 'user', 'ai', 'rule'
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    tag = relationship("DocumentTag", back_populates="document_assignments")
    document = relationship("Document", back_populates="tag_assignments")

    def __repr__(self):
        return f"<DocumentTagAssignment(document='{self.document_id}', tag='{self.tag_id}', confidence={self.confidence_score})>"


# Enhanced DocumentChunk model for vector storage (update to existing model)
class DocumentChunkCategorization:
    """
    This represents the additional fields to be added to the existing DocumentChunk model
    in shared/models/vector_models.py for categorization support.

    These fields should be added to the existing DocumentChunk class:

    category_ids = Column(ARRAY(String(36)), default=list, nullable=False)
    tag_ids = Column(ARRAY(String(36)), default=list, nullable=False)
    content_type = Column(String(50), nullable=True)  # 'text', 'table', 'list', etc.
    """
    pass


# Pydantic models for API responses
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class DocumentCategoryResponse(BaseModel):
    """Response model for document categories."""
    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    parent_category_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_system_category: bool = False
    document_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentTagResponse(BaseModel):
    """Response model for document tags."""
    id: str
    tenant_id: str
    name: str
    tag_type: str
    usage_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentCategoryAssignmentResponse(BaseModel):
    """Response model for document category assignments."""
    document_id: str
    category_id: str
    confidence_score: float
    assigned_by: str
    assigned_at: datetime
    category: Optional[DocumentCategoryResponse] = None

    class Config:
        from_attributes = True


class DocumentTagAssignmentResponse(BaseModel):
    """Response model for document tag assignments."""
    document_id: str
    tag_id: str
    confidence_score: float
    assigned_by: str
    assigned_at: datetime
    tag: Optional[DocumentTagResponse] = None

    class Config:
        from_attributes = True


class DocumentClassificationRequest(BaseModel):
    """Request model for manual document classification."""
    document_id: str
    categories: Optional[List[str]] = None  # Category names or IDs
    tags: Optional[List[str]] = None  # Tag names or IDs
    auto_categorize: bool = True


class DocumentClassificationResponse(BaseModel):
    """Response model for document classification results."""
    document_id: str
    categories: List[DocumentCategoryAssignmentResponse]
    tags: List[DocumentTagAssignmentResponse]
    auto_classification: Optional[dict] = None  # AI classification results
    classification_confidence: float = 0.0

    class Config:
        from_attributes = True


class CategoryCreateRequest(BaseModel):
    """Request model for creating categories."""
    name: str
    description: Optional[str] = None
    parent_category_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class TagCreateRequest(BaseModel):
    """Request model for creating tags."""
    name: str
    tag_type: str = 'custom'


class CategoryStatistics(BaseModel):
    """Statistics for document categories."""
    category_name: str
    total_documents: int
    total_chunks: int
    avg_confidence: float
    ai_vs_manual: dict


class DocumentSearchFilters(BaseModel):
    """Filters for document search."""
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    content_type: Optional[str] = None
    confidence_threshold: Optional[float] = None