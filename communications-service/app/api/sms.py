from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.database import get_db
from ..core.config import settings
from ..services.sms_service import SMSService
from ..services.dependencies import validate_token, validate_super_admin_token, TokenClaims
from ..models.communications import SmsMessage, MessageStatus
from ..core.logging_config import set_request_context, clear_request_context

router = APIRouter()


class SMSSendRequest(BaseModel):
    """Request model for sending SMS"""
    to_phone: str
    message: str
    from_phone: Optional[str] = None
    template_id: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None


class SMSSendResponse(BaseModel):
    """Response model for SMS send"""
    message_id: str
    success: bool
    message: str


class SMSMessageResponse(BaseModel):
    """Response model for SMS message details"""
    id: str
    tenant_id: str
    to_phone: str
    from_phone: str
    message: str
    status: str
    created_at: str
    sent_at: Optional[str]
    delivered_at: Optional[str]
    error_message: Optional[str]


class SMSListResponse(BaseModel):
    """Response model for SMS list"""
    messages: List[SMSMessageResponse]
    total: int
    page: int
    size: int


def _convert_sms_to_response(sms: SmsMessage) -> SMSMessageResponse:
    """Convert SmsMessage model to response"""
    return SMSMessageResponse(
        id=sms.id,
        tenant_id=sms.tenant_id,
        to_phone=sms.to_phone,
        from_phone=sms.from_phone,
        message=sms.message,
        status=sms.status.value,
        created_at=sms.created_at.isoformat(),
        sent_at=sms.sent_at.isoformat() if sms.sent_at else None,
        delivered_at=sms.delivered_at.isoformat() if sms.delivered_at else None,
        error_message=sms.error_message
    )


@router.post("/send", response_model=SMSSendResponse)
async def send_sms(
    request: SMSSendRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Send SMS message (requires Bearer token authentication)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="send_sms"
    )

    try:
        # Validate message length
        if len(request.message) > settings.MAX_SMS_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SMS message exceeds {settings.MAX_SMS_LENGTH} character limit"
            )

        # Validate phone number format (basic validation)
        if not request.to_phone.startswith('+'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number must include country code (e.g., +1234567890)"
            )

        # Send SMS
        sms_service = SMSService(db)
        message_id, success = sms_service.send_sms(
            tenant_id=claims.tenant_id,
            to_phone=request.to_phone,
            message=request.message,
            from_phone=request.from_phone,
            template_id=request.template_id,
            template_data=request.template_data
        )

        return SMSSendResponse(
            message_id=message_id,
            success=success,
            message="SMS sent successfully" if success else "SMS send failed"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send SMS: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/messages", response_model=SMSListResponse)
async def get_tenant_sms(
    page: int = 1,
    size: int = 50,
    status_filter: Optional[MessageStatus] = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get SMS history for the authenticated tenant"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="list_sms"
    )

    try:
        # Validate pagination
        if page < 1:
            page = 1
        if size < 1 or size > settings.MAX_PAGE_SIZE:
            size = min(size, settings.MAX_PAGE_SIZE)

        skip = (page - 1) * size

        # Get SMS messages
        sms_service = SMSService(db)
        messages = sms_service.get_tenant_sms(
            tenant_id=claims.tenant_id,
            skip=skip,
            limit=size,
            status=status_filter
        )

        # Get total count
        query = db.query(SmsMessage).filter(SmsMessage.tenant_id == claims.tenant_id)
        if status_filter:
            query = query.filter(SmsMessage.status == status_filter)
        total = query.count()

        # Convert to response format
        sms_responses = [_convert_sms_to_response(sms) for sms in messages]

        return SMSListResponse(
            messages=sms_responses,
            total=total,
            page=page,
            size=size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get SMS messages: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/messages/{message_id}", response_model=SMSMessageResponse)
async def get_sms_details(
    message_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get details of a specific SMS message"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="get_sms_details"
    )

    try:
        sms_service = SMSService(db)
        sms = sms_service.get_sms_status(message_id, claims.tenant_id)

        if not sms:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SMS message not found"
            )

        return _convert_sms_to_response(sms)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get SMS details: {str(e)}"
        )
    finally:
        clear_request_context()


# Super Admin Routes
@router.get("/admin/messages/{tenant_id}", response_model=SMSListResponse)
async def get_tenant_sms_admin(
    tenant_id: str,
    page: int = 1,
    size: int = 50,
    status_filter: Optional[MessageStatus] = None,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db)
):
    """Get SMS history for a specific tenant (super admin only)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="admin_list_sms",
        target_tenant=tenant_id
    )

    try:
        # Validate pagination
        if page < 1:
            page = 1
        if size < 1 or size > settings.MAX_PAGE_SIZE:
            size = min(size, settings.MAX_PAGE_SIZE)

        skip = (page - 1) * size

        # Get SMS messages
        sms_service = SMSService(db)
        messages = sms_service.get_tenant_sms(
            tenant_id=tenant_id,
            skip=skip,
            limit=size,
            status=status_filter
        )

        # Get total count
        query = db.query(SmsMessage).filter(SmsMessage.tenant_id == tenant_id)
        if status_filter:
            query = query.filter(SmsMessage.status == status_filter)
        total = query.count()

        # Convert to response format
        sms_responses = [_convert_sms_to_response(sms) for sms in messages]

        return SMSListResponse(
            messages=sms_responses,
            total=total,
            page=page,
            size=size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get SMS messages: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/admin/statistics/{tenant_id}")
async def get_sms_statistics(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db)
):
    """Get SMS statistics for a specific tenant (super admin only)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="admin_sms_statistics",
        target_tenant=tenant_id
    )

    try:
        # Get SMS statistics
        stats = {}
        for status in MessageStatus:
            count = db.query(SmsMessage).filter(
                SmsMessage.tenant_id == tenant_id,
                SmsMessage.status == status
            ).count()
            stats[status.value] = count

        # Get total SMS messages
        total = db.query(SmsMessage).filter(SmsMessage.tenant_id == tenant_id).count()

        return {
            "tenant_id": tenant_id,
            "total_sms": total,
            "status_breakdown": stats,
            "generated_at": "2024-01-01T00:00:00Z"  # Current timestamp would go here
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get SMS statistics: {str(e)}"
        )
    finally:
        clear_request_context()


@router.post("/webhooks/provider")
async def handle_sms_webhook(webhook_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Handle SMS provider webhook events"""

    try:
        sms_service = SMSService(db)
        success = sms_service.handle_webhook(webhook_data)

        if success:
            return {"message": "Webhook processed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process webhook"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )