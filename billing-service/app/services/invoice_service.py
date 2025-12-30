"""
Invoice Generation and Management Service

Handles:
- Automatic invoice generation on payment
- Invoice retrieval and history
- PDF invoice generation
- Invoice status management
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models.subscription import (
    Invoice,
    Payment,
    Subscription,
    PaymentStatus
)
from ..models.plan import Plan
from ..core.logging_config import get_logger
from ..utils.logo_utils import get_logo_data_url

logger = get_logger("invoice-service")


class InvoiceService:
    """Service for managing invoices"""

    def __init__(self, db: Session):
        self.db = db

    def generate_invoice_number(self) -> str:
        """
        Generate unique invoice number.

        Format: INV-YYYYMMDD-NNNN
        Example: INV-20251118-0001
        """
        today = datetime.now(timezone.utc)
        date_prefix = today.strftime("%Y%m%d")

        # Find the latest invoice for today
        latest_invoice = (
            self.db.query(Invoice)
            .filter(Invoice.invoice_number.like(f"INV-{date_prefix}-%"))
            .order_by(Invoice.created_at.desc())
            .first()
        )

        if latest_invoice:
            # Extract sequence number and increment
            last_sequence = int(latest_invoice.invoice_number.split("-")[-1])
            new_sequence = last_sequence + 1
        else:
            new_sequence = 1

        return f"INV-{date_prefix}-{new_sequence:04d}"

    def create_invoice(
        self,
        subscription_id: str,
        tenant_id: str,
        amount: Decimal,
        currency: str,
        period_start: datetime,
        period_end: datetime,
        line_items: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None
    ) -> Invoice:
        """
        Create a new invoice.

        Args:
            subscription_id: Subscription ID
            tenant_id: Tenant ID
            amount: Invoice amount
            currency: Currency code (NGN, USD, etc.)
            period_start: Billing period start date
            period_end: Billing period end date
            line_items: Detailed billing items
            notes: Additional notes

        Returns:
            Created invoice object
        """
        try:
            # Generate invoice number
            invoice_number = self.generate_invoice_number()

            # Calculate due date (typically 7 days from creation)
            due_date = datetime.now(timezone.utc) + timedelta(days=7)

            # Default line items if not provided
            if line_items is None:
                subscription = self.db.query(Subscription).filter(
                    Subscription.id == subscription_id
                ).first()

                plan = self.db.query(Plan).filter(
                    Plan.id == subscription.plan_id
                ).first() if subscription else None

                line_items = [{
                    "description": f"{plan.name} Plan - {subscription.billing_cycle}" if plan else "Subscription",
                    "quantity": 1,
                    "unit_price": float(amount),
                    "total": float(amount)
                }]

            # Create invoice
            invoice = Invoice(
                subscription_id=subscription_id,
                tenant_id=tenant_id,
                invoice_number=invoice_number,
                status=PaymentStatus.PENDING.value,
                subtotal=amount,
                tax_amount=Decimal("0.00"),  # No tax for now
                total_amount=amount,
                currency=currency,
                period_start=period_start,
                period_end=period_end,
                due_date=due_date,
                line_items=line_items,
                notes=notes
            )

            self.db.add(invoice)
            self.db.commit()
            self.db.refresh(invoice)

            logger.info(
                f"Invoice created: {invoice_number}",
                extra={
                    "invoice_id": invoice.id,
                    "subscription_id": subscription_id,
                    "tenant_id": tenant_id,
                    "amount": float(amount)
                }
            )

            return invoice

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to create invoice: {e}",
                exc_info=True,
                extra={"subscription_id": subscription_id}
            )
            raise

    def create_invoice_from_payment(self, payment: Payment) -> Optional[Invoice]:
        """
        Automatically create invoice from payment.

        Args:
            payment: Payment object

        Returns:
            Created invoice or None if already exists
        """
        try:
            # Check if invoice already exists for this payment
            existing_invoice = self.db.query(Invoice).filter(
                and_(
                    Invoice.subscription_id == payment.subscription_id,
                    Invoice.period_start == payment.created_at,
                    Invoice.status == PaymentStatus.COMPLETED.value
                )
            ).first()

            if existing_invoice:
                logger.info(f"Invoice already exists for payment {payment.id}")
                return existing_invoice

            # Get subscription details
            subscription = self.db.query(Subscription).filter(
                Subscription.id == payment.subscription_id
            ).first()

            if not subscription:
                logger.error(f"Subscription not found: {payment.subscription_id}")
                return None

            # Create invoice
            invoice = self.create_invoice(
                subscription_id=payment.subscription_id,
                tenant_id=subscription.tenant_id,
                amount=payment.amount,
                currency=payment.currency,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
                notes=f"Payment reference: {payment.paystack_reference}"
            )

            # Mark invoice as paid immediately (since payment already completed)
            invoice.status = PaymentStatus.COMPLETED.value
            invoice.paid_at = payment.created_at
            self.db.commit()

            logger.info(
                f"Invoice created from payment",
                extra={
                    "invoice_id": invoice.id,
                    "payment_id": payment.id,
                    "subscription_id": subscription.id
                }
            )

            return invoice

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to create invoice from payment: {e}",
                exc_info=True,
                extra={"payment_id": payment.id}
            )
            return None

    def get_invoice_by_id(self, invoice_id: str) -> Optional[Invoice]:
        """Get invoice by ID"""
        return self.db.query(Invoice).filter(Invoice.id == invoice_id).first()

    def get_invoice_by_number(self, invoice_number: str) -> Optional[Invoice]:
        """Get invoice by invoice number"""
        return self.db.query(Invoice).filter(
            Invoice.invoice_number == invoice_number
        ).first()

    def get_invoices_by_tenant(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get paginated invoice history for tenant.

        Args:
            tenant_id: Tenant ID
            limit: Maximum number of invoices to return
            offset: Number of invoices to skip

        Returns:
            Dictionary with invoices and pagination info
        """
        try:
            # Get total count
            total = self.db.query(Invoice).filter(
                Invoice.tenant_id == tenant_id
            ).count()

            # Get invoices with pagination
            invoices = (
                self.db.query(Invoice)
                .filter(Invoice.tenant_id == tenant_id)
                .order_by(Invoice.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            # Format response
            invoice_list = []
            for invoice in invoices:
                invoice_list.append({
                    "id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "status": invoice.status,
                    "total_amount": float(invoice.total_amount),
                    "currency": invoice.currency,
                    "period_start": invoice.period_start.isoformat(),
                    "period_end": invoice.period_end.isoformat(),
                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                    "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
                    "created_at": invoice.created_at.isoformat(),
                    "line_items": invoice.line_items
                })

            return {
                "invoices": invoice_list,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }

        except Exception as e:
            logger.error(
                f"Failed to get invoices for tenant: {e}",
                exc_info=True,
                extra={"tenant_id": tenant_id}
            )
            raise

    def get_invoices_by_subscription(
        self,
        subscription_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Invoice]:
        """Get invoices for a specific subscription"""
        return (
            self.db.query(Invoice)
            .filter(Invoice.subscription_id == subscription_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def mark_invoice_as_paid(
        self,
        invoice_id: str,
        paid_at: Optional[datetime] = None
    ) -> Invoice:
        """
        Mark invoice as paid.

        Args:
            invoice_id: Invoice ID
            paid_at: Payment date (defaults to now)

        Returns:
            Updated invoice
        """
        try:
            invoice = self.get_invoice_by_id(invoice_id)
            if not invoice:
                raise ValueError(f"Invoice not found: {invoice_id}")

            invoice.status = PaymentStatus.COMPLETED.value
            invoice.paid_at = paid_at or datetime.now(timezone.utc)

            self.db.commit()
            self.db.refresh(invoice)

            logger.info(
                f"Invoice marked as paid: {invoice.invoice_number}",
                extra={"invoice_id": invoice_id}
            )

            return invoice

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to mark invoice as paid: {e}",
                exc_info=True,
                extra={"invoice_id": invoice_id}
            )
            raise

    def cancel_invoice(self, invoice_id: str) -> Invoice:
        """
        Cancel an invoice.

        Args:
            invoice_id: Invoice ID

        Returns:
            Updated invoice
        """
        try:
            invoice = self.get_invoice_by_id(invoice_id)
            if not invoice:
                raise ValueError(f"Invoice not found: {invoice_id}")

            if invoice.status == PaymentStatus.COMPLETED.value:
                raise ValueError("Cannot cancel a paid invoice")

            invoice.status = PaymentStatus.CANCELLED.value

            self.db.commit()
            self.db.refresh(invoice)

            logger.info(
                f"Invoice cancelled: {invoice.invoice_number}",
                extra={"invoice_id": invoice_id}
            )

            return invoice

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Failed to cancel invoice: {e}",
                exc_info=True,
                extra={"invoice_id": invoice_id}
            )
            raise

    def generate_invoice_html(self, invoice_id: str) -> str:
        """
        Generate HTML representation of invoice.

        Args:
            invoice_id: Invoice ID

        Returns:
            HTML string
        """
        invoice = self.get_invoice_by_id(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice not found: {invoice_id}")

        # Get subscription and plan details
        subscription = self.db.query(Subscription).filter(
            Subscription.id == invoice.subscription_id
        ).first()

        plan = self.db.query(Plan).filter(
            Plan.id == subscription.plan_id
        ).first() if subscription else None

        # Format currency
        currency_symbol = "₦" if invoice.currency == "NGN" else invoice.currency

        # Build line items HTML
        line_items_html = ""
        for item in invoice.line_items:
            line_items_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">{item.get('description', '')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">{item.get('quantity', 1)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{currency_symbol}{item.get('unit_price', 0):,.2f}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{currency_symbol}{item.get('total', 0):,.2f}</td>
            </tr>
            """

        # Get logo data URL for PDF (base64-embedded)
        logo_data_url = get_logo_data_url("chatcraft-logo.png")

        # Generate HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice {invoice.invoice_number}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .invoice-container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ display: flex; justify-content: space-between; margin-bottom: 30px; align-items: center; }}
                .company-info {{ }}
                .invoice-info {{ text-align: right; }}
                .invoice-title {{ font-size: 32px; font-weight: bold; color: #2B55FF; margin-bottom: 10px; }}
                .logo {{ max-width: 60px; height: auto; margin-bottom: 8px; }}
                .status-badge {{ display: inline-block; padding: 5px 15px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
                .status-completed {{ background-color: #4CAF50; color: white; }}
                .status-pending {{ background-color: #FF9800; color: white; }}
                .status-cancelled {{ background-color: #F44336; color: white; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background-color: #f5f5f5; padding: 12px; text-align: left; border-bottom: 2px solid #ddd; }}
                .totals {{ margin-top: 20px; text-align: right; }}
                .totals-row {{ margin: 10px 0; }}
                .grand-total {{ font-size: 20px; font-weight: bold; color: #2B55FF; }}
                .highlight-bar {{ background-color: #CDF547; height: 4px; width: 60px; margin: 10px 0; }}
                .footer {{ margin-top: 50px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; color: #888; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="invoice-container">
                <!-- Header -->
                <div class="header">
                    <div class="company-info">
                        {f'<img src="{logo_data_url}" alt="ChatCraft Logo" class="logo">' if logo_data_url else ''}
                        <div class="highlight-bar"></div>
                        <div class="invoice-title">ChatCraft</div>
                        <p>
                            support@chatcraft.cc<br>
                            https://www.chatcraft.cc
                        </p>
                    </div>
                    <div class="invoice-info">
                        <h2>INVOICE</h2>
                        <p>
                            <strong>Invoice Number:</strong> {invoice.invoice_number}<br>
                            <strong>Status:</strong> <span class="status-badge status-{invoice.status.lower()}">{invoice.status.upper()}</span><br>
                            <strong>Date:</strong> {invoice.created_at.strftime('%B %d, %Y')}<br>
                            <strong>Due Date:</strong> {invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else 'N/A'}
                        </p>
                    </div>
                </div>

                <!-- Billing Information -->
                <div style="margin-bottom: 30px;">
                    <h3>Bill To:</h3>
                    <p>
                        <strong>{subscription.user_full_name or 'Valued Customer'}</strong><br>
                        {subscription.user_email or ''}<br>
                        Tenant ID: {invoice.tenant_id}
                    </p>
                </div>

                <!-- Billing Period -->
                <div style="margin-bottom: 20px; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #2B55FF;">
                    <strong>Billing Period:</strong> {invoice.period_start.strftime('%B %d, %Y')} - {invoice.period_end.strftime('%B %d, %Y')}
                </div>

                <!-- Line Items -->
                <table>
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th style="text-align: center;">Quantity</th>
                            <th style="text-align: right;">Unit Price</th>
                            <th style="text-align: right;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {line_items_html}
                    </tbody>
                </table>

                <!-- Totals -->
                <div class="totals">
                    <div class="totals-row">
                        <strong>Subtotal:</strong> {currency_symbol}{float(invoice.subtotal):,.2f}
                    </div>
                    <div class="totals-row">
                        <strong>Tax:</strong> {currency_symbol}{float(invoice.tax_amount):,.2f}
                    </div>
                    <div class="totals-row grand-total">
                        <strong>Total:</strong> {currency_symbol}{float(invoice.total_amount):,.2f}
                    </div>
                    {f'<div class="totals-row" style="color: #4CAF50;"><strong>Paid:</strong> {invoice.paid_at.strftime("%B %d, %Y")}</div>' if invoice.paid_at else ''}
                </div>

                <!-- Notes -->
                {f'<div style="margin-top: 30px;"><strong>Notes:</strong><p>{invoice.notes}</p></div>' if invoice.notes else ''}

                <!-- Footer -->
                <div class="footer">
                    <p>Thank you for your business!</p>
                    <p>This is a computer-generated invoice. For questions, contact support@chatcraft.cc</p>
                    <p style="margin-top: 10px; color: #2B55FF;">
                        <strong>ChatCraft</strong> - AI-Powered Chat Solutions
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def generate_invoice_pdf(self, invoice_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate PDF for an existing invoice.

        Args:
            invoice_id: ID of the invoice to generate PDF for

        Returns:
            Tuple of (pdf_bytes, error_message)
            - On success: (pdf_bytes, None)
            - On failure: (None, error_message)
        """
        from datetime import datetime, timezone
        from .pdf_generator import PDFGenerator

        try:
            # Get invoice from database
            invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if not invoice:
                return None, "Invoice not found"

            # Generate HTML
            html_content = self.generate_invoice_html(invoice_id)

            # Generate PDF
            pdf_generator = PDFGenerator()
            pdf_bytes, error = pdf_generator.generate_invoice_pdf(
                html_content=html_content,
                invoice_number=invoice.invoice_number
            )

            # Update invoice record
            if pdf_bytes:
                invoice.pdf_generated_at = datetime.now(timezone.utc)
                invoice.pdf_generation_error = None
            else:
                invoice.pdf_generation_error = error

            self.db.commit()

            return pdf_bytes, error

        except Exception as e:
            logger.error(f"Failed to generate PDF for invoice {invoice_id}: {str(e)}", exc_info=True)
            return None, f"PDF generation failed: {str(e)}"

    def create_invoice_with_pdf(
        self,
        payment: Payment,
        document_type: str = "invoice"
    ) -> Tuple[Optional[Invoice], Optional[bytes]]:
        """
        Create an invoice from a payment and generate its PDF in one operation.

        Args:
            payment: Payment record to create invoice from
            document_type: Type of document (invoice, refund, credit_memo)

        Returns:
            Tuple of (invoice, pdf_bytes)
            - On success: (invoice, pdf_bytes) or (invoice, None) if PDF generation failed
            - On failure: (None, None)
        """
        from .pdf_generator import PDFGenerator

        try:
            # Create invoice from payment
            invoice = self.create_invoice_from_payment(payment)

            if not invoice:
                logger.error(f"Failed to create invoice from payment {payment.id}")
                return None, None

            # Update document type and bidirectional payment-invoice relationship
            invoice.document_type = document_type
            invoice.related_payment_id = payment.id  # Backward compatibility
            payment.invoice_id = invoice.id  # NEW: Set bidirectional relationship

            self.db.add(invoice)
            self.db.add(payment)  # Ensure payment is updated
            self.db.commit()
            self.db.refresh(invoice)
            self.db.refresh(payment)

            # Generate PDF
            pdf_bytes, error = self.generate_invoice_pdf(invoice.id)

            if error:
                logger.warning(
                    f"Invoice {invoice.invoice_number} created but PDF generation failed: {error}"
                )

            return invoice, pdf_bytes

        except Exception as e:
            logger.error(
                f"Failed to create invoice with PDF for payment {payment.id}: {str(e)}",
                exc_info=True
            )
            return None, None
