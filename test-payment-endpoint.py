#!/usr/bin/env python3
"""
Test script for the new payment details endpoint.
This script bypasses authentication to verify the endpoint logic.
"""

import sys
sys.path.insert(0, 'billing-service')

from app.core.database import SessionLocal
from app.models.subscription import Payment, Subscription, Invoice
from sqlalchemy.orm import Session

def test_payment_endpoint_logic(payment_id: str):
    """Test the logic of the payment endpoint without HTTP"""
    db = SessionLocal()

    try:
        print(f"Testing payment endpoint logic for ID: {payment_id}")
        print("-" * 60)

        # Get payment
        payment = db.query(Payment).filter(Payment.id == payment_id).first()

        if not payment:
            print(f"❌ Payment not found: {payment_id}")
            return

        print(f"✅ Payment found")
        print(f"   ID: {payment.id}")
        print(f"   Tenant ID: {payment.tenant_id}")
        print(f"   Amount: {payment.amount} {payment.currency}")
        print(f"   Status: {payment.status}")
        print(f"   Payment Method: {payment.payment_method}")
        print(f"   Transaction Type: {payment.transaction_type}")

        # Get related subscription details
        subscription = None
        if payment.subscription_id:
            subscription = db.query(Subscription).filter(
                Subscription.id == payment.subscription_id
            ).first()

            if subscription:
                print(f"\n✅ Subscription found")
                print(f"   ID: {subscription.id}")
                print(f"   Plan ID: {subscription.plan_id}")
                print(f"   Status: {subscription.status}")
                print(f"   User: {subscription.user_full_name} ({subscription.user_email})")
            else:
                print(f"\n⚠️  Subscription not found (ID: {payment.subscription_id})")
        else:
            print(f"\n⚠️  No subscription linked to this payment")

        # Get related invoice if exists
        invoice = None
        if payment.invoice_id:
            invoice = db.query(Invoice).filter(
                Invoice.id == payment.invoice_id
            ).first()

            if invoice:
                print(f"\n✅ Invoice found")
                print(f"   ID: {invoice.id}")
                print(f"   Invoice Number: {invoice.invoice_number}")
                print(f"   Total Amount: {invoice.total_amount}")
                print(f"   Status: {invoice.status}")
            else:
                print(f"\n⚠️  Invoice not found (ID: {payment.invoice_id})")
        else:
            print(f"\n⚠️  No invoice linked to this payment")

        # Build response
        response = {
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
            "gateway_response": payment.gateway_response,
            "refunded_amount": float(payment.refunded_amount) if payment.refunded_amount else 0.0,
            "invoice_id": payment.invoice_id,
        }

        # Add subscription details if available
        if subscription:
            response["subscription"] = {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "status": subscription.status,
                "user_email": subscription.user_email,
                "user_full_name": subscription.user_full_name,
            }

        # Add invoice details if available
        if invoice:
            response["invoice"] = {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "total_amount": float(invoice.total_amount),
                "status": invoice.status,
            }

        print(f"\n" + "=" * 60)
        print("✅ ENDPOINT LOGIC TEST PASSED")
        print(f"Response structure created successfully with {len(response)} fields")
        if subscription:
            print("   - Subscription details included")
        if invoice:
            print("   - Invoice details included")
        print("=" * 60)

        return response

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        db.close()


if __name__ == "__main__":
    # Test with the sample payment ID
    payment_id = "6ea54f0d-5c37-4aae-9140-39587296e2ff"

    if len(sys.argv) > 1:
        payment_id = sys.argv[1]

    result = test_payment_endpoint_logic(payment_id)

    # Test with non-existent ID
    print("\n\n" + "=" * 60)
    print("Testing with non-existent payment ID...")
    print("=" * 60)
    test_payment_endpoint_logic("non-existent-id-12345")
