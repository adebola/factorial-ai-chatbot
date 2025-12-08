"""
API endpoints for subscription restriction checking.

These endpoints are used by other services (chat, onboarding) to validate
tenant permissions before allowing operations.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..core.database import get_db
from ..services.subscription_checker import SubscriptionChecker, SubscriptionRestrictionError

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class SubscriptionStatusResponse(BaseModel):
    """Response model for subscription status check"""
    is_active: bool
    reason: Optional[str] = None


class PermissionCheckResponse(BaseModel):
    """Response model for permission checks"""
    allowed: bool
    reason: Optional[str] = None


class UsageSummaryResponse(BaseModel):
    """Response model for usage summary"""
    subscription_status: str
    plan_name: str
    documents: dict
    websites: dict
    monthly_chats: dict


# Endpoints
@router.get("/check/subscription/{tenant_id}", response_model=SubscriptionStatusResponse)
async def check_subscription_status(
    tenant_id: str,
    include_grace_period: bool = True,
    db: Session = Depends(get_db)
):
    """
    Check if tenant has an active subscription.

    This endpoint is called by other services to validate subscription status
    before allowing tenant operations.

    Args:
        tenant_id: Tenant ID to check
        include_grace_period: Whether to include 3-day grace period for past_due

    Returns:
        SubscriptionStatusResponse with status and reason
    """
    logger.info(f"Checking subscription status for tenant {tenant_id}")

    checker = SubscriptionChecker(db)
    is_active, reason = checker.check_subscription_active(
        tenant_id=tenant_id,
        include_grace_period=include_grace_period
    )

    return SubscriptionStatusResponse(
        is_active=is_active,
        reason=reason
    )


@router.get("/check/can-upload-document/{tenant_id}", response_model=PermissionCheckResponse)
async def check_can_upload_document(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """
    Check if tenant can upload a document based on subscription and plan limits.

    Called by onboarding-service before allowing document uploads.

    Args:
        tenant_id: Tenant ID to check

    Returns:
        PermissionCheckResponse with allowed status and reason
    """
    logger.info(f"Checking document upload permission for tenant {tenant_id}")

    checker = SubscriptionChecker(db)
    can_upload, reason = checker.check_can_upload_document(tenant_id)

    return PermissionCheckResponse(
        allowed=can_upload,
        reason=reason
    )


@router.get("/check/can-ingest-website/{tenant_id}", response_model=PermissionCheckResponse)
async def check_can_ingest_website(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """
    Check if tenant can ingest a website based on subscription and plan limits.

    Called by onboarding-service before allowing website ingestion.

    Args:
        tenant_id: Tenant ID to check

    Returns:
        PermissionCheckResponse with allowed status and reason
    """
    logger.info(f"Checking website ingestion permission for tenant {tenant_id}")

    checker = SubscriptionChecker(db)
    can_ingest, reason = checker.check_can_ingest_website(tenant_id)

    return PermissionCheckResponse(
        allowed=can_ingest,
        reason=reason
    )


@router.get("/check/can-send-chat/{tenant_id}", response_model=PermissionCheckResponse)
async def check_can_send_chat(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """
    Check if tenant can send a chat message based on subscription and plan limits.

    Called by chat-service before processing chat messages.

    Args:
        tenant_id: Tenant ID to check

    Returns:
        PermissionCheckResponse with allowed status and reason
    """
    logger.info(f"Checking chat permission for tenant {tenant_id}")

    checker = SubscriptionChecker(db)
    can_chat, reason = checker.check_can_send_chat(tenant_id)

    return PermissionCheckResponse(
        allowed=can_chat,
        reason=reason
    )


@router.get("/usage/{tenant_id}", response_model=UsageSummaryResponse)
async def get_usage_summary(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive usage summary for a tenant.

    Returns current usage and limits for documents, websites, and chats.

    Args:
        tenant_id: Tenant ID

    Returns:
        UsageSummaryResponse with detailed usage information

    Raises:
        404: If no active subscription found
    """
    logger.info(f"Getting usage summary for tenant {tenant_id}")

    checker = SubscriptionChecker(db)
    summary = checker.get_usage_summary(tenant_id)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found for this tenant"
        )

    return summary
