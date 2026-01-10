"""
Admin API Endpoints for System Administrators

These endpoints require SYSTEM_ADMIN role and provide cross-tenant access
to billing data for Factorial Systems staff.
"""
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import uuid

from ..core.database import get_db
from ..services.dependencies import require_system_admin, TokenClaims
from ..services.subscription_service import SubscriptionService
from ..services.audit_service import AuditService
from ..services.invoice_service import InvoiceService
from ..models.subscription import (
    Subscription, Payment, PaymentMethod, PaymentStatus,
    TransactionType, Invoice
)

router = APIRouter(prefix="/billing/admin", tags=["Admin - Billing"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class PaginatedResponse(BaseModel):
    """Standard paginated response"""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool


class ManualPaymentRequest(BaseModel):
    """Request schema for creating manual payments"""
    tenant_id: str = Field(..., description="Tenant ID for the payment")
    subscription_id: str = Field(..., description="Subscription ID to apply payment to")
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    payment_method: str = Field(..., description="Payment method (e.g., 'bank_transfer', 'cash', 'check')")
    payment_date: datetime = Field(default_factory=datetime.now, description="Date of payment")
    reference_number: Optional[str] = Field(None, description="Bank transfer reference, check number, etc.")
    notes: str = Field(..., description="Reason for manual payment")
    should_extend_subscription: bool = Field(True, description="Whether to extend subscription period")
    extension_days: int = Field(30, description="Number of days to extend subscription")
    send_confirmation_email: bool = Field(True, description="Send email confirmation to customer")


class ManualPaymentResponse(BaseModel):
    """Response schema for manual payment creation"""
    success: bool
    payment_id: str
    invoice_number: Optional[str]
    subscription_status: str
    new_period_end: datetime
    message: str


class SubscriptionOverrideRequest(BaseModel):
    """Request schema for subscription overrides"""
    new_plan_id: Optional[str] = Field(None, description="Change to different plan")
    custom_expiration: Optional[datetime] = Field(None, description="Set custom expiration date")
    trial_extension_days: Optional[int] = Field(None, description="Extend trial by N days")
    usage_limit_overrides: Optional[Dict[str, int]] = Field(None, description="Override usage limits")
    reason: str = Field(..., description="Reason for override")


# ============================================================================
# Subscription Endpoints
# ============================================================================

@router.get("/subscriptions")
async def list_all_subscriptions(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=500, description="Page size"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    plan_id: Optional[str] = Query(None, description="Filter by plan ID"),
    search: Optional[str] = Query(None, description="Search by tenant name or email"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    List subscriptions across all tenants (SYSTEM_ADMIN only).

    **Query Parameters:**
    - `page`: Page number (default: 1)
    - `size`: Page size (default: 50, max: 500)
    - `tenant_id`: Filter by specific tenant
    - `status`: Filter by subscription status
    - `plan_id`: Filter by plan ID
    - `search`: Search by tenant name or email

    **Returns:**
    Paginated list of subscriptions with tenant details.
    """
    try:
        query = db.query(Subscription)

        # Apply filters
        if tenant_id:
            query = query.filter(Subscription.tenant_id == tenant_id)

        if status:
            query = query.filter(Subscription.status == status)

        if plan_id:
            query = query.filter(Subscription.plan_id == plan_id)

        # TODO: Implement search across tenant name/email (requires join with authorization server)

        # Get total count
        total = query.count()

        # Paginate
        subscriptions = (
            query
            .order_by(Subscription.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        # Calculate pagination metadata
        pages = (total + size - 1) // size
        has_next = page < pages
        has_prev = page > 1

        return {
            "items": [
                {
                    "id": sub.id,
                    "tenant_id": sub.tenant_id,
                    "plan_id": sub.plan_id,
                    "status": sub.status,
                    "billing_cycle": sub.billing_cycle,
                    "amount": float(sub.amount),
                    "currency": sub.currency,
                    "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
                    "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                    "user_email": sub.user_email,
                    "user_full_name": sub.user_full_name,
                    "created_at": sub.created_at.isoformat(),
                }
                for sub in subscriptions
            ],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
            "has_next": has_next,
            "has_prev": has_prev,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve subscriptions: {str(e)}"
        )


# ============================================================================
# Payment Endpoints
# ============================================================================

@router.get("/payments")
async def list_all_payments(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=500, description="Page size"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    status: Optional[str] = Query(None, description="Filter by payment status"),
    payment_method: Optional[str] = Query(None, description="Filter by payment method"),
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    List payments across all tenants (SYSTEM_ADMIN only).

    **Query Parameters:**
    - `page`: Page number (default: 1)
    - `size`: Page size (default: 50, max: 500)
    - `tenant_id`: Filter by specific tenant
    - `status`: Filter by payment status
    - `payment_method`: Filter by payment method

    **Returns:**
    Paginated list of payments.
    """
    try:
        query = db.query(Payment)

        # Apply filters
        if tenant_id:
            query = query.filter(Payment.tenant_id == tenant_id)

        if status:
            query = query.filter(Payment.status == status)

        if payment_method:
            query = query.filter(Payment.payment_method == payment_method)

        # Get total count
        total = query.count()

        # Paginate
        payments = (
            query
            .order_by(Payment.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        # Calculate pagination metadata
        pages = (total + size - 1) // size
        has_next = page < pages
        has_prev = page > 1

        return {
            "items": [
                {
                    "id": payment.id,
                    "tenant_id": payment.tenant_id,
                    "subscription_id": payment.subscription_id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "status": payment.status,
                    "payment_method": payment.payment_method,
                    "transaction_type": payment.transaction_type,
                    "paystack_reference": payment.paystack_reference,
                    "description": payment.description,
                    "created_at": payment.created_at.isoformat(),
                    "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
                }
                for payment in payments
            ],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
            "has_next": has_next,
            "has_prev": has_prev,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve payments: {str(e)}"
        )


@router.post("/payments/manual", response_model=ManualPaymentResponse)
async def create_manual_payment(
    payment_data: ManualPaymentRequest,
    request: Request,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Create manual payment for offline transactions (SYSTEM_ADMIN only).

    This endpoint allows system administrators to record payments received
    via offline methods (bank transfer, cash, check, etc.).

    **Process:**
    1. Create payment record (COMPLETED status)
    2. Extend subscription period (if requested)
    3. Generate invoice
    4. Log admin action
    5. Send confirmation email (if requested)

    **Example:**
    ```json
    {
      "tenant_id": "abc-123",
      "subscription_id": "sub-456",
      "amount": 50000.00,
      "payment_method": "bank_transfer",
      "reference_number": "TRF-20260103-001",
      "notes": "Bank transfer received on Jan 3, 2026",
      "should_extend_subscription": true,
      "extension_days": 30,
      "send_confirmation_email": true
    }
    ```
    """
    try:
        # Get subscription before state
        subscription = db.query(Subscription).filter(
            Subscription.id == payment_data.subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription not found: {payment_data.subscription_id}"
            )

        if subscription.tenant_id != payment_data.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription does not belong to specified tenant"
            )

        before_state = {
            "status": subscription.status,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        }

        # Create manual payment record
        payment_id = str(uuid.uuid4())
        payment_reference = payment_data.reference_number or f"manual_{payment_data.payment_method}_{payment_id[:8]}"

        payment = Payment(
            id=payment_id,
            subscription_id=payment_data.subscription_id,
            tenant_id=payment_data.tenant_id,
            amount=payment_data.amount,
            currency=subscription.currency or "NGN",
            status=PaymentStatus.COMPLETED,
            payment_method=payment_data.payment_method,
            transaction_type=TransactionType.RENEWAL,
            paystack_reference=payment_reference,
            description=payment_data.notes,
            created_at=payment_data.payment_date,
            processed_at=payment_data.payment_date,
            gateway_response={"manual_payment": True, "processed_by_admin": claims.user_id},
            refunded_amount=Decimal("0.00")
        )
        db.add(payment)

        # Extend subscription if requested
        invoice_number = None
        if payment_data.should_extend_subscription:
            # Determine new period start
            if subscription.status == "expired":
                new_period_start = datetime.now()
            else:
                new_period_start = subscription.current_period_end or datetime.now()

            # Calculate new period end
            new_period_end = new_period_start + timedelta(days=payment_data.extension_days)

            # Update subscription
            subscription.current_period_start = new_period_start
            subscription.current_period_end = new_period_end
            subscription.ends_at = new_period_end
            subscription.status = "active"
            subscription.updated_at = datetime.now()

            # Generate invoice
            invoice_service = InvoiceService(db)
            invoice_number = invoice_service.generate_invoice_number()

            invoice = Invoice(
                id=str(uuid.uuid4()),
                invoice_number=invoice_number,
                subscription_id=subscription.id,
                tenant_id=subscription.tenant_id,
                subtotal=payment_data.amount,
                tax_amount=Decimal("0.00"),
                total_amount=payment_data.amount,
                currency=subscription.currency or "NGN",
                status="completed",
                period_start=new_period_start,
                period_end=new_period_end,
                due_date=datetime.now(),
                notes=payment_data.notes,
                created_at=datetime.now(),
                paid_at=datetime.now()
            )
            db.add(invoice)

            # Link payment to invoice
            payment.invoice_id = invoice.id

        db.commit()
        db.refresh(subscription)
        db.refresh(payment)

        # Get subscription after state
        after_state = {
            "status": subscription.status,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        }

        result = {
            "payment_id": payment_id,
            "invoice_number": invoice_number
        }

        # Log admin action
        audit_service = AuditService(db)
        audit_service.log_action(
            admin_claims=claims,
            action_type="manual_payment",
            target_type="payment",
            target_id=result["payment_id"],
            target_tenant_id=payment_data.tenant_id,
            before_state=before_state,
            after_state=after_state,
            reason=payment_data.notes,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata={
                "amount": float(payment_data.amount),
                "payment_method": payment_data.payment_method,
                "reference_number": payment_data.reference_number,
                "extension_days": payment_data.extension_days,
            }
        )

        # TODO: Send confirmation email if requested
        # if payment_data.send_confirmation_email:
        #     email_publisher.publish_manual_payment_confirmation(...)

        return ManualPaymentResponse(
            success=True,
            payment_id=result["payment_id"],
            invoice_number=result.get("invoice_number"),
            subscription_status=subscription.status,
            new_period_end=subscription.current_period_end,
            message=f"Manual payment recorded successfully for tenant {payment_data.tenant_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create manual payment: {str(e)}"
        )


# ============================================================================
# Subscription Override Endpoints
# ============================================================================

@router.post("/subscriptions/{subscription_id}/override")
async def override_subscription(
    subscription_id: str,
    override_data: SubscriptionOverrideRequest,
    request: Request,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """
    Override subscription settings for special cases (SYSTEM_ADMIN only).

    Allows:
    - Custom expiration dates
    - Trial extensions
    - Plan changes without payment
    - Usage limit overrides

    **Example:**
    ```json
    {
      "custom_expiration": "2026-12-31T23:59:59Z",
      "reason": "Special promotion for valued customer"
    }
    ```
    """
    try:
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription not found: {subscription_id}"
            )

        # Capture before state
        before_state = {
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        }

        # Apply overrides
        if override_data.new_plan_id:
            subscription.plan_id = override_data.new_plan_id

        if override_data.custom_expiration:
            subscription.current_period_end = override_data.custom_expiration
            subscription.ends_at = override_data.custom_expiration

        if override_data.trial_extension_days:
            if subscription.trial_end:
                from datetime import timedelta
                subscription.trial_end = subscription.trial_end + timedelta(days=override_data.trial_extension_days)

        # TODO: Implement usage_limit_overrides (requires additional metadata storage)

        db.commit()
        db.refresh(subscription)

        # Capture after state
        after_state = {
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
        }

        # Log admin action
        audit_service = AuditService(db)
        audit_service.log_action(
            admin_claims=claims,
            action_type="subscription_override",
            target_type="subscription",
            target_id=subscription_id,
            target_tenant_id=subscription.tenant_id,
            before_state=before_state,
            after_state=after_state,
            reason=override_data.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata={
                "new_plan_id": override_data.new_plan_id,
                "custom_expiration": override_data.custom_expiration.isoformat() if override_data.custom_expiration else None,
                "trial_extension_days": override_data.trial_extension_days,
            }
        )

        return {
            "success": True,
            "subscription_id": subscription_id,
            "message": "Subscription override applied successfully",
            "subscription": {
                "id": subscription.id,
                "status": subscription.status,
                "plan_id": subscription.plan_id,
                "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to override subscription: {str(e)}"
        )
