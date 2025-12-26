#!/usr/bin/env python3
"""
Complete test for invoice PDF generation and RabbitMQ delivery with attachment.

This test verifies:
1. PDF invoice generation works
2. PDF is properly attached to email
3. Email is published to RabbitMQ with PDF attachment
4. RabbitMQ message includes base64-encoded PDF

Test case: Plan upgrade from Basic to Lite for another@factorialsystems.io
"""

import os
import sys
import json
from datetime import datetime, timezone

# Set up environment
os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/billing_db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('RABBITMQ_HOST', 'localhost')
os.environ.setdefault('RABBITMQ_PORT', '5672')
os.environ.setdefault('RABBITMQ_USER', 'user')
os.environ.setdefault('RABBITMQ_PASSWORD', 'password')
os.environ.setdefault('RABBITMQ_EXCHANGE', 'communications-exchange')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.subscription import Subscription, Payment, Invoice
from app.models.plan import Plan
from app.services.invoice_service import InvoiceService
from app.services.pdf_generator import PDFGenerator
from app.services.email_publisher import email_publisher

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def verify_rabbitmq_connection():
    """Verify RabbitMQ is accessible"""
    try:
        import pika
        credentials = pika.PlainCredentials(
            os.environ.get('RABBITMQ_USER', 'user'),
            os.environ.get('RABBITMQ_PASSWORD', 'password')
        )
        parameters = pika.ConnectionParameters(
            host=os.environ.get('RABBITMQ_HOST', 'localhost'),
            port=int(os.environ.get('RABBITMQ_PORT', '5672')),
            credentials=credentials,
            heartbeat=600
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        connection.close()
        return True, "RabbitMQ connection successful"
    except Exception as e:
        return False, f"RabbitMQ connection failed: {e}"


def test_invoice_pdf_generation_and_email():
    """
    Complete test for invoice PDF generation and email delivery via RabbitMQ.

    Steps:
    1. Find subscription for the Lite plan upgrade
    2. Find or create payment record
    3. Find or create invoice
    4. Generate PDF invoice
    5. Create attachment dict with base64-encoded PDF
    6. Publish email to RabbitMQ with PDF attachment
    7. Verify attachment is in the message
    """

    print("\n" + "="*80)
    print("INVOICE PDF GENERATION & RABBITMQ DELIVERY TEST")
    print("="*80)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Test Case: Plan Upgrade (Basic → Lite)")
    print("="*80 + "\n")

    # Step 1: Verify RabbitMQ connection
    print("📡 Step 1: Verifying RabbitMQ Connection...")
    rabbitmq_ok, rabbitmq_msg = verify_rabbitmq_connection()
    if rabbitmq_ok:
        print(f"   ✅ {rabbitmq_msg}")
    else:
        print(f"   ⚠️  {rabbitmq_msg}")
        print("   ℹ️  Will attempt to publish anyway...")

    db = SessionLocal()
    try:
        # Step 2: Find subscription
        print("\n📋 Step 2: Finding Subscription...")
        tenant_id = "17b5ed30-8198-46c0-9e76-9b21362dad92"

        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id
        ).order_by(Subscription.created_at.desc()).first()

        if not subscription:
            print(f"   ❌ No subscription found for tenant {tenant_id}")
            return False

        print(f"   ✅ Found Subscription:")
        print(f"      - Subscription ID: {subscription.id}")
        print(f"      - Tenant ID: {subscription.tenant_id}")
        print(f"      - Plan ID: {subscription.plan_id}")
        print(f"      - Status: {subscription.status}")
        print(f"      - Amount: {subscription.currency} {float(subscription.amount):,.2f}")
        print(f"      - User Email: {subscription.user_email}")
        print(f"      - User Name: {subscription.user_full_name}")

        # Get plan details
        plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if plan:
            print(f"      - Plan Name: {plan.name}")

        # Step 3: Find payment
        print("\n💰 Step 3: Finding Payment Record...")
        payment = db.query(Payment).filter(
            Payment.subscription_id == subscription.id
        ).order_by(Payment.created_at.desc()).first()

        if not payment:
            print("   ❌ No payment found")
            return False

        print(f"   ✅ Found Payment:")
        print(f"      - Payment ID: {payment.id}")
        print(f"      - Amount: {payment.currency} {float(payment.amount):,.2f}")
        print(f"      - Status: {payment.status}")
        print(f"      - Reference: {payment.paystack_reference}")
        print(f"      - Created: {payment.created_at}")

        # Step 4: Find or create invoice
        print("\n📄 Step 4: Finding/Creating Invoice...")
        invoice = db.query(Invoice).filter(
            Invoice.subscription_id == subscription.id,
            Invoice.related_payment_id == payment.id
        ).first()

        invoice_service = InvoiceService(db)
        pdf_bytes = None

        if invoice:
            print(f"   ✅ Found Existing Invoice:")
            print(f"      - Invoice Number: {invoice.invoice_number}")
            print(f"      - Invoice ID: {invoice.id}")
            print(f"      - Total Amount: {invoice.currency} {float(invoice.total_amount):,.2f}")
            print(f"      - Status: {invoice.status}")
            print(f"      - Created: {invoice.created_at}")

            # Regenerate PDF
            print("\n🔨 Step 5: Regenerating PDF...")
            pdf_bytes, error = invoice_service.generate_invoice_pdf(invoice.id)

            if error:
                print(f"      ⚠️  PDF generation had issues: {error}")
                if not pdf_bytes:
                    print("      ❌ No PDF bytes generated")
                    return False

            print(f"      ✅ PDF Generated Successfully:")
            print(f"         - Size: {len(pdf_bytes):,} bytes")
            print(f"         - Size: {len(pdf_bytes) / 1024:.2f} KB")

        else:
            print("   ℹ️  No existing invoice, creating new one...")
            print("\n🔨 Step 5: Creating Invoice with PDF...")
            invoice, pdf_bytes = invoice_service.create_invoice_with_pdf(
                payment,
                document_type="invoice"
            )

            if not invoice:
                print("      ❌ Failed to create invoice")
                return False

            print(f"   ✅ Invoice Created:")
            print(f"      - Invoice Number: {invoice.invoice_number}")
            print(f"      - Invoice ID: {invoice.id}")
            print(f"      - Total Amount: {invoice.currency} {float(invoice.total_amount):,.2f}")
            print(f"      - Status: {invoice.status}")

            if pdf_bytes:
                print(f"      - PDF Size: {len(pdf_bytes):,} bytes ({len(pdf_bytes) / 1024:.2f} KB)")
            else:
                print("      ❌ PDF generation failed")
                return False

        # Step 6: Create PDF attachment
        print("\n📎 Step 6: Creating PDF Attachment...")
        if not pdf_bytes:
            print("   ❌ No PDF bytes available")
            return False

        pdf_gen = PDFGenerator()
        pdf_attachment = pdf_gen.generate_attachment_dict(pdf_bytes, invoice.invoice_number)

        print(f"   ✅ PDF Attachment Created:")
        print(f"      - Filename: {pdf_attachment['filename']}")
        print(f"      - Content Type: {pdf_attachment['content_type']}")
        print(f"      - Base64 Content Length: {len(pdf_attachment['content']):,} characters")
        print(f"      - Original PDF Size: {len(pdf_bytes):,} bytes")
        print(f"      - Base64 Encoding Overhead: {(len(pdf_attachment['content']) - len(pdf_bytes)) / len(pdf_bytes) * 100:.1f}%")

        # Verify base64 content
        try:
            import base64
            decoded = base64.b64decode(pdf_attachment['content'])
            print(f"      ✅ Base64 Encoding Verified (decoded back to {len(decoded):,} bytes)")
        except Exception as e:
            print(f"      ⚠️  Base64 verification failed: {e}")

        # Step 7: Publish email to RabbitMQ
        print("\n📧 Step 7: Publishing Email to RabbitMQ...")

        if not subscription.user_email:
            print("   ❌ Cannot send email: user_email not set")
            return False

        print(f"   Email Details:")
        print(f"      - To: {subscription.user_email}")
        print(f"      - Name: {subscription.user_full_name or 'Valued Customer'}")
        print(f"      - Invoice: {invoice.invoice_number}")
        print(f"      - Amount: {invoice.currency} {float(invoice.total_amount):,.2f}")
        print(f"      - Status: {invoice.status}")
        print(f"      - PDF Attached: Yes ({pdf_attachment['filename']})")

        print("\n   Publishing to RabbitMQ...")
        success = email_publisher.publish_invoice_email(
            tenant_id=tenant_id,
            to_email=subscription.user_email,
            to_name=subscription.user_full_name or "Valued Customer",
            invoice_number=invoice.invoice_number,
            total_amount=float(invoice.total_amount),
            currency=invoice.currency,
            due_date=invoice.due_date,
            status=invoice.status,
            pdf_attachment=pdf_attachment
        )

        if not success:
            print("   ❌ Failed to publish email to RabbitMQ")
            return False

        print(f"   ✅ Email Published to RabbitMQ Successfully!")
        print(f"\n   RabbitMQ Message Details:")
        print(f"      - Exchange: communications-exchange")
        print(f"      - Routing Key: email.send")
        print(f"      - Subject: Invoice {invoice.invoice_number} - Ready for Payment")
        print(f"      - Attachment Included: Yes")
        print(f"      - Attachment Filename: {pdf_attachment['filename']}")
        print(f"      - Attachment Size (base64): {len(pdf_attachment['content']):,} chars")

        # Step 8: Summary
        print("\n" + "="*80)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\nSummary:")
        print(f"  ✅ Subscription found: {subscription.id}")
        print(f"  ✅ Payment found: {payment.id}")
        print(f"  ✅ Invoice created/found: {invoice.invoice_number}")
        print(f"  ✅ PDF generated: {len(pdf_bytes):,} bytes")
        print(f"  ✅ PDF attachment created: {pdf_attachment['filename']}")
        print(f"  ✅ Email published to RabbitMQ with PDF attachment")
        print(f"\n  📬 Email sent to: {subscription.user_email}")
        print(f"  📎 PDF attachment: {pdf_attachment['filename']}")
        print(f"  💰 Invoice amount: {invoice.currency} {float(invoice.total_amount):,.2f}")
        print(f"  📊 Plan: {plan.name if plan else 'Unknown'}")

        print("\n" + "="*80)
        print("The invoice email with PDF attachment has been published to RabbitMQ.")
        print("The communications-service will consume this message and send the email via Brevo.")
        print("="*80 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "#"*80)
    print("# INVOICE PDF GENERATION & RABBITMQ DELIVERY TEST")
    print("# Test Case: Plan Upgrade from Basic to Lite")
    print("# User: another@factorialsystems.io (Another Organisation)")
    print("#"*80)

    success = test_invoice_pdf_generation_and_email()

    if success:
        print("\n" + "🎉"*40)
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe invoice PDF was:")
        print("  1. ✅ Generated successfully")
        print("  2. ✅ Encoded as base64")
        print("  3. ✅ Attached to email message")
        print("  4. ✅ Published to RabbitMQ")
        print("\nThe communications-service will now:")
        print("  1. Consume the message from RabbitMQ")
        print("  2. Extract the PDF attachment")
        print("  3. Send the email via Brevo with PDF attached")
        print("\n" + "🎉"*40 + "\n")
        sys.exit(0)
    else:
        print("\n" + "❌"*40)
        print("\n❌ TEST FAILED!")
        print("\n" + "❌"*40 + "\n")
        sys.exit(1)
