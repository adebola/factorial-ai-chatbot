"""
PDF Generation Service

This service handles converting HTML invoices to PDF format using WeasyPrint.
It provides methods for generating PDFs, encoding them for email attachments,
and creating attachment dictionaries for RabbitMQ message publishing.
"""

import base64
import logging
from typing import Optional, Tuple, Dict
from io import BytesIO

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Service for generating PDF documents from HTML content"""

    def __init__(self):
        """Initialize PDF generator"""
        if not WEASYPRINT_AVAILABLE:
            logger.warning(
                "WeasyPrint is not installed. PDF generation will fail. "
                "Install with: pip install weasyprint"
            )
        self.font_config = FontConfiguration() if WEASYPRINT_AVAILABLE else None

    def generate_invoice_pdf(
        self,
        html_content: str,
        invoice_number: str
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate a PDF invoice from HTML content.

        Args:
            html_content: HTML string containing the invoice
            invoice_number: Invoice number for logging purposes

        Returns:
            Tuple of (pdf_bytes, error_message)
            - On success: (pdf_bytes, None)
            - On failure: (None, error_message)
        """
        if not WEASYPRINT_AVAILABLE:
            error_msg = "WeasyPrint library is not available"
            logger.error(f"PDF generation failed for {invoice_number}: {error_msg}")
            return None, error_msg

        try:
            logger.info(f"Generating PDF for invoice {invoice_number}")

            # Create PDF from HTML
            pdf_file = BytesIO()
            HTML(string=html_content).write_pdf(
                pdf_file,
                font_config=self.font_config
            )

            # Get PDF bytes
            pdf_bytes = pdf_file.getvalue()
            pdf_file.close()

            logger.info(
                f"Successfully generated PDF for invoice {invoice_number} "
                f"({len(pdf_bytes)} bytes)"
            )

            return pdf_bytes, None

        except Exception as e:
            error_msg = f"PDF generation failed: {str(e)}"
            logger.error(
                f"Failed to generate PDF for invoice {invoice_number}: {error_msg}",
                exc_info=True
            )
            return None, error_msg

    def pdf_to_base64(self, pdf_bytes: bytes) -> str:
        """
        Convert PDF bytes to base64 string for email attachment.

        Args:
            pdf_bytes: PDF file as bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(pdf_bytes).decode('utf-8')

    def generate_attachment_dict(
        self,
        pdf_bytes: bytes,
        invoice_number: str
    ) -> Dict[str, str]:
        """
        Generate attachment dictionary for RabbitMQ email message.

        Args:
            pdf_bytes: PDF file as bytes
            invoice_number: Invoice number for filename

        Returns:
            Dictionary with attachment data:
            {
                "filename": "invoice-INV-001.pdf",
                "content": "<base64_encoded_pdf>",
                "content_type": "application/pdf"
            }
        """
        return {
            "filename": f"invoice-{invoice_number}.pdf",
            "content": self.pdf_to_base64(pdf_bytes),
            "content_type": "application/pdf"
        }

    def generate_refund_attachment_dict(
        self,
        pdf_bytes: bytes,
        invoice_number: str
    ) -> Dict[str, str]:
        """
        Generate attachment dictionary for refund credit memo.

        Args:
            pdf_bytes: PDF file as bytes
            invoice_number: Invoice number for filename

        Returns:
            Dictionary with attachment data for refund credit memo
        """
        return {
            "filename": f"refund-{invoice_number}.pdf",
            "content": self.pdf_to_base64(pdf_bytes),
            "content_type": "application/pdf"
        }
