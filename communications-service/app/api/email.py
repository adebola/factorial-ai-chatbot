import base64
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from ..core.database import get_db
from ..core.config import settings
from ..services.email_service import EmailService
from ..services.dependencies import validate_token, validate_super_admin_token, TokenClaims
from ..models.communications import EmailMessage, MessageStatus
from ..core.logging_config import set_request_context, clear_request_context

router = APIRouter()


class EmailSendRequest(BaseModel):
    """Request model for sending email"""
    to_email: EmailStr
    subject: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    to_name: Optional[str] = None
    template_id: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None


class EmailSendResponse(BaseModel):
    """Response model for email send"""
    message_id: str
    success: bool
    message: str


class EmailMessageResponse(BaseModel):
    """Response model for email message details"""
    id: str
    tenant_id: str
    to_email: str
    to_name: Optional[str]
    from_email: str
    from_name: Optional[str]
    subject: str
    status: str
    created_at: str
    sent_at: Optional[str]
    delivered_at: Optional[str]
    opened_at: Optional[str]
    clicked_at: Optional[str]
    error_message: Optional[str]
    attachments: Optional[List[Dict[str, Any]]]


class EmailListResponse(BaseModel):
    """Response model for email list"""
    emails: List[EmailMessageResponse]
    total: int
    page: int
    size: int


def _convert_email_to_response(email: EmailMessage) -> EmailMessageResponse:
    """Convert EmailMessage model to response"""
    return EmailMessageResponse(
        id=email.id,
        tenant_id=email.tenant_id,
        to_email=email.to_email,
        to_name=email.to_name,
        from_email=email.from_email,
        from_name=email.from_name,
        subject=email.subject,
        status=email.status.value,
        created_at=email.created_at.isoformat(),
        sent_at=email.sent_at.isoformat() if email.sent_at else None,
        delivered_at=email.delivered_at.isoformat() if email.delivered_at else None,
        opened_at=email.opened_at.isoformat() if email.opened_at else None,
        clicked_at=email.clicked_at.isoformat() if email.clicked_at else None,
        error_message=email.error_message,
        attachments=email.attachments
    )


@router.post("/send", response_model=EmailSendResponse)
async def send_email_with_attachments(
    to_email: EmailStr = Form(...),
    subject: str = Form(...),
    html_content: Optional[str] = Form(None),
    text_content: Optional[str] = Form(None),
    to_name: Optional[str] = Form(None),
    template_id: Optional[str] = Form(None),
    template_data: Optional[str] = Form(None),  # JSON string
    attachments: List[UploadFile] = File([]),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Send email with optional attachments (requires Bearer token authentication)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="send_email"
    )

    try:
        # Validate content
        if not html_content and not text_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either html_content or text_content must be provided"
            )

        # Validate attachments
        attachment_data = []
        if attachments:
            if len(attachments) > settings.MAX_ATTACHMENTS_PER_EMAIL:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Maximum {settings.MAX_ATTACHMENTS_PER_EMAIL} attachments allowed"
                )

            total_size = 0
            for attachment in attachments:
                content = await attachment.read()
                size = len(content)
                total_size += size

                # Check individual file size
                if size > settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Attachment {attachment.filename} exceeds {settings.MAX_ATTACHMENT_SIZE_MB}MB limit"
                    )

                # Encode content as base64
                encoded_content = base64.b64encode(content).decode()

                attachment_data.append({
                    "filename": attachment.filename,
                    "content": encoded_content,
                    "content_type": attachment.content_type,
                    "size": size
                })

            # Check total size
            if total_size > settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Total attachment size exceeds {settings.MAX_ATTACHMENT_SIZE_MB}MB limit"
                )

        # Parse template_data if provided
        parsed_template_data = None
        if template_data:
            try:
                import json
                parsed_template_data = json.loads(template_data)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON in template_data"
                )

        # Send email
        email_service = EmailService(db)
        message_id, success = email_service.send_email(
            tenant_id=claims.tenant_id,
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            to_name=to_name,
            attachments=attachment_data if attachment_data else None,
            # template_id=template_id,
            template_data=parsed_template_data
        )

        return EmailSendResponse(
            message_id=message_id,
            success=success,
            message="Email sent successfully" if success else "Email send failed"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/messages", response_model=EmailListResponse)
async def get_tenant_emails(
    page: int = 1,
    size: int = 50,
    status_filter: Optional[MessageStatus] = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get email history for the authenticated tenant"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="list_emails"
    )

    try:
        # Validate pagination
        if page < 1:
            page = 1
        if size < 1 or size > settings.MAX_PAGE_SIZE:
            size = min(size, settings.MAX_PAGE_SIZE)

        skip = (page - 1) * size

        # Get emails
        email_service = EmailService(db)
        emails = email_service.get_tenant_emails(
            tenant_id=claims.tenant_id,
            skip=skip,
            limit=size,
            status=status_filter
        )

        # Get total count
        query = db.query(EmailMessage).filter(EmailMessage.tenant_id == claims.tenant_id)
        if status_filter:
            query = query.filter(EmailMessage.status == status_filter)
        total = query.count()

        # Convert to response format
        email_responses = [_convert_email_to_response(email) for email in emails]

        return EmailListResponse(
            emails=email_responses,
            total=total,
            page=page,
            size=size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emails: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/messages/{message_id}", response_model=EmailMessageResponse)
async def get_email_details(
    message_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """Get details of a specific email message"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="get_email_details"
    )

    try:
        email_service = EmailService(db)
        email = email_service.get_email_status(message_id, claims.tenant_id)

        if not email:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found"
            )

        return _convert_email_to_response(email)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get email details: {str(e)}"
        )
    finally:
        clear_request_context()


# Super Admin Routes
@router.get("/admin/messages/{tenant_id}", response_model=EmailListResponse)
async def get_tenant_emails_admin(
    tenant_id: str,
    page: int = 1,
    size: int = 50,
    status_filter: Optional[MessageStatus] = None,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db)
):
    """Get email history for a specific tenant (super admin only)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="admin_list_emails",
        target_tenant=tenant_id
    )

    try:
        # Validate pagination
        if page < 1:
            page = 1
        if size < 1 or size > settings.MAX_PAGE_SIZE:
            size = min(size, settings.MAX_PAGE_SIZE)

        skip = (page - 1) * size

        # Get emails
        email_service = EmailService(db)
        emails = email_service.get_tenant_emails(
            tenant_id=tenant_id,
            skip=skip,
            limit=size,
            status=status_filter
        )

        # Get total count
        query = db.query(EmailMessage).filter(EmailMessage.tenant_id == tenant_id)
        if status_filter:
            query = query.filter(EmailMessage.status == status_filter)
        total = query.count()

        # Convert to response format
        email_responses = [_convert_email_to_response(email) for email in emails]

        return EmailListResponse(
            emails=email_responses,
            total=total,
            page=page,
            size=size
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emails: {str(e)}"
        )
    finally:
        clear_request_context()


@router.get("/admin/statistics/{tenant_id}")
async def get_email_statistics(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_super_admin_token),
    db: Session = Depends(get_db)
):
    """Get email statistics for a specific tenant (super admin only)"""

    # Set request context for logging
    set_request_context(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        operation="admin_email_statistics",
        target_tenant=tenant_id
    )

    try:
        # Get email statistics
        stats = {}
        for status in MessageStatus:
            count = db.query(EmailMessage).filter(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.status == status
            ).count()
            stats[status.value] = count

        # Get total emails
        total = db.query(EmailMessage).filter(EmailMessage.tenant_id == tenant_id).count()

        return {
            "tenant_id": tenant_id,
            "total_emails": total,
            "status_breakdown": stats,
            "generated_at": "2024-01-01T00:00:00Z"  # Current timestamp would go here
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get email statistics: {str(e)}"
        )
    finally:
        clear_request_context()


@router.post("/webhooks/sendgrid")
async def handle_sendgrid_webhook(webhook_data: List[Dict[str, Any]], db: Session = Depends(get_db)):
    """Handle SendGrid webhook events"""

    try:
        email_service = EmailService(db)
        success = email_service.handle_webhook(webhook_data)

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