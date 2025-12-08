"""
Invoice API Endpoints

Handles:
- Invoice history retrieval
- Individual invoice details
- Invoice PDF/HTML generation
- Invoice email delivery
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Dict, Any

from ..core.database import get_db
from ..services.dependencies import validate_token, TokenClaims
from ..services.invoice_service import InvoiceService
from ..services.email_publisher import email_publisher
from ..models.subscription import Invoice

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
async def get_invoices(
    limit: int = 50,
    offset: int = 0,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get invoice history for the authenticated tenant.

    **Query Parameters**:
    - `limit`: Maximum number of invoices to return (default: 50)
    - `offset`: Number of invoices to skip for pagination (default: 0)

    **Returns**:
    - List of invoices with pagination metadata

    **Example Response**:
    ```json
    {
      "invoices": [
        {
          "id": "inv-123",
          "invoice_number": "INV-20251118-0001",
          "status": "completed",
          "total_amount": 9.99,
          "currency": "NGN",
          "period_start": "2025-11-01T00:00:00Z",
          "period_end": "2025-12-01T00:00:00Z",
          "paid_at": "2025-11-01T10:30:00Z",
          "created_at": "2025-11-01T09:00:00Z"
        }
      ],
      "total": 5,
      "limit": 50,
      "offset": 0,
      "has_more": false
    }
    ```
    """
    try:
        invoice_service = InvoiceService(db)
        result = invoice_service.get_invoices_by_tenant(
            tenant_id=claims.tenant_id,
            limit=limit,
            offset=offset
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve invoices: {str(e)}"
        )


@router.get("/{invoice_id}", response_model=Dict[str, Any])
async def get_invoice(
    invoice_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed information about a specific invoice.

    **Path Parameters**:
    - `invoice_id`: UUID of the invoice

    **Returns**:
    - Detailed invoice information including line items

    **Example Response**:
    ```json
    {
      "id": "inv-123",
      "invoice_number": "INV-20251118-0001",
      "subscription_id": "sub-456",
      "status": "completed",
      "subtotal": 9.99,
      "tax_amount": 0.00,
      "total_amount": 9.99,
      "currency": "NGN",
      "period_start": "2025-11-01T00:00:00Z",
      "period_end": "2025-12-01T00:00:00Z",
      "due_date": "2025-11-08T00:00:00Z",
      "paid_at": "2025-11-01T10:30:00Z",
      "line_items": [
        {
          "description": "Basic Plan - monthly",
          "quantity": 1,
          "unit_price": 9.99,
          "total": 9.99
        }
      ],
      "notes": "Payment reference: PAY_123456",
      "created_at": "2025-11-01T09:00:00Z"
    }
    ```
    """
    try:
        invoice_service = InvoiceService(db)
        invoice = invoice_service.get_invoice_by_id(invoice_id)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found"
            )

        # Verify invoice belongs to tenant
        if invoice.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own invoices"
            )

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subscription_id": invoice.subscription_id,
            "status": invoice.status,
            "subtotal": float(invoice.subtotal),
            "tax_amount": float(invoice.tax_amount),
            "total_amount": float(invoice.total_amount),
            "currency": invoice.currency,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "line_items": invoice.line_items,
            "notes": invoice.notes,
            "created_at": invoice.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve invoice: {str(e)}"
        )


@router.get("/{invoice_id}/html", response_class=HTMLResponse)
async def get_invoice_html(
    invoice_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> str:
    """
    Get HTML representation of invoice for viewing/printing.

    **Path Parameters**:
    - `invoice_id`: UUID of the invoice

    **Returns**:
    - Formatted HTML invoice

    **Use Cases**:
    - Display invoice in browser
    - Print invoice
    - Generate PDF from HTML (future)
    """
    try:
        invoice_service = InvoiceService(db)
        invoice = invoice_service.get_invoice_by_id(invoice_id)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found"
            )

        # Verify invoice belongs to tenant
        if invoice.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own invoices"
            )

        html = invoice_service.generate_invoice_html(invoice_id)
        return html

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invoice HTML: {str(e)}"
        )


@router.post("/{invoice_id}/send", response_model=Dict[str, Any])
async def send_invoice_email(
    invoice_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Send invoice via email to customer.

    **Path Parameters**:
    - `invoice_id`: UUID of the invoice

    **Returns**:
    - Success confirmation

    **Email Content**:
    - Invoice number and amount
    - Payment status
    - Link to view invoice online
    - Download options
    """
    try:
        invoice_service = InvoiceService(db)
        invoice = invoice_service.get_invoice_by_id(invoice_id)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found"
            )

        # Verify invoice belongs to tenant
        if invoice.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only send your own invoices"
            )

        # Get subscription for user email
        from ..models.subscription import Subscription
        subscription = db.query(Subscription).filter(
            Subscription.id == invoice.subscription_id
        ).first()

        if not subscription or not subscription.user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No email address found for this subscription"
            )

        # Send invoice email
        success = email_publisher.publish_invoice_email(
            tenant_id=invoice.tenant_id,
            to_email=subscription.user_email,
            to_name=subscription.user_full_name or "Valued Customer",
            invoice_number=invoice.invoice_number,
            total_amount=float(invoice.total_amount),
            currency=invoice.currency,
            due_date=invoice.due_date,
            status=invoice.status
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send invoice email"
            )

        return {
            "success": True,
            "message": f"Invoice {invoice.invoice_number} sent to {subscription.user_email}",
            "invoice_id": invoice_id,
            "sent_to": subscription.user_email
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send invoice email: {str(e)}"
        )


@router.get("/number/{invoice_number}", response_model=Dict[str, Any])
async def get_invoice_by_number(
    invoice_number: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get invoice by invoice number (e.g., INV-20251118-0001).

    **Path Parameters**:
    - `invoice_number`: Invoice number

    **Returns**:
    - Detailed invoice information
    """
    try:
        invoice_service = InvoiceService(db)
        invoice = invoice_service.get_invoice_by_number(invoice_number)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice not found: {invoice_number}"
            )

        # Verify invoice belongs to tenant
        if invoice.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own invoices"
            )

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subscription_id": invoice.subscription_id,
            "status": invoice.status,
            "subtotal": float(invoice.subtotal),
            "tax_amount": float(invoice.tax_amount),
            "total_amount": float(invoice.total_amount),
            "currency": invoice.currency,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "line_items": invoice.line_items,
            "notes": invoice.notes,
            "created_at": invoice.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve invoice: {str(e)}"
        )
