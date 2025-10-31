# Import all models to ensure they are registered with SQLAlchemy
# Note: Tenant and TenantSettings models have been migrated to OAuth2 Authorization Server
# Note: Billing models (Subscription, Payment, etc.) have been migrated to Billing Service
from .tenant import Base, Plan, Document, WebsiteIngestion, WebsitePage
from .categorization import (
    DocumentCategory,
    DocumentTag,
    DocumentCategoryAssignment,
    DocumentTagAssignment,
    DocumentClassification,
    DocumentCategoryResponse,
    DocumentTagResponse,
    DocumentCategoryAssignmentResponse,
    DocumentTagAssignmentResponse,
    DocumentClassificationRequest,
    DocumentClassificationResponse,
    CategoryCreateRequest,
    TagCreateRequest,
    CategoryStatistics,
    DocumentSearchFilters
)

__all__ = [
    "Base",
    "Plan",
    "Document",
    "WebsiteIngestion",
    "WebsitePage",
    "DocumentCategory",
    "DocumentTag",
    "DocumentCategoryAssignment",
    "DocumentTagAssignment",
    "DocumentClassification",
    "DocumentCategoryResponse",
    "DocumentTagResponse",
    "DocumentCategoryAssignmentResponse",
    "DocumentTagAssignmentResponse",
    "DocumentClassificationRequest",
    "DocumentClassificationResponse",
    "CategoryCreateRequest",
    "TagCreateRequest",
    "CategoryStatistics",
    "DocumentSearchFilters",
]