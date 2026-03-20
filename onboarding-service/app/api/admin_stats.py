from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from ..core.database import get_db
from ..models.tenant import Document, WebsiteIngestion, DocumentStatus, IngestionStatus
from ..core.logging_config import get_logger
from ..services.dependencies import require_system_admin, TokenClaims

router = APIRouter()
logger = get_logger("onboarding")


@router.get("/admin/stats")
async def get_onboarding_stats(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID (system admin only)"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Get onboarding statistics (system admin only - cross-tenant or filtered by tenant)"""

    logger.info("System admin getting onboarding stats", user_id=claims.user_id, tenant_id=tenant_id)

    # Build base queries - can be filtered by tenant or system-wide
    document_query = db.query(Document)
    website_query = db.query(WebsiteIngestion)

    if tenant_id:
        document_query = document_query.filter(Document.tenant_id == tenant_id)
        website_query = website_query.filter(WebsiteIngestion.tenant_id == tenant_id)

    # Get document statistics
    num_documents = document_query.count()
    documents_pending = document_query.filter(Document.status == DocumentStatus.PENDING).count()
    documents_processing = document_query.filter(Document.status == DocumentStatus.PROCESSING).count()
    documents_completed = document_query.filter(Document.status == DocumentStatus.COMPLETED).count()
    documents_failed = document_query.filter(Document.status == DocumentStatus.FAILED).count()

    # Get website statistics
    num_websites = website_query.count()
    websites_pending = website_query.filter(WebsiteIngestion.status == IngestionStatus.PENDING).count()
    websites_in_progress = website_query.filter(WebsiteIngestion.status == IngestionStatus.IN_PROGRESS).count()
    websites_completed = website_query.filter(WebsiteIngestion.status == IngestionStatus.COMPLETED).count()
    websites_failed = website_query.filter(WebsiteIngestion.status == IngestionStatus.FAILED).count()

    # Calculate storage used in MB with proper conditional filtering
    storage_query = db.query(func.sum(Document.file_size))
    if tenant_id:
        storage_query = storage_query.filter(Document.tenant_id == tenant_id)

    total_storage_bytes = storage_query.scalar() or 0
    storage_used_mb = round(total_storage_bytes / (1024 * 1024), 2)

    stats = {
        "num_documents": num_documents,
        "documents_by_status": {
            "pending": documents_pending,
            "processing": documents_processing,
            "completed": documents_completed,
            "failed": documents_failed
        },
        "num_websites": num_websites,
        "websites_by_status": {
            "pending": websites_pending,
            "in_progress": websites_in_progress,
            "completed": websites_completed,
            "failed": websites_failed
        },
        "storage_used_mb": storage_used_mb,
        "tenant_id": tenant_id if tenant_id else "all_tenants"
    }

    logger.info("System admin retrieved onboarding stats", stats=stats, filtered_tenant=tenant_id)
    return stats
