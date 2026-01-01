"""
Manual Subscription Extension for Offline Payments

This script allows administrators to manually extend subscriptions for clients
who have paid via offline methods (bank transfer, cash, etc.) while maintaining
data integrity.

Usage:
    python manual_subscription_extension.py <tenant_id>

Example:
    python manual_subscription_extension.py a72627cd-0169-434a-9ce1-a694709e329e
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/billing_db")

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def get_tenant_subscription(session, tenant_id: str):
    """Get active or expired subscription for tenant"""
    result = session.execute(
        text("""
            SELECT
                s.id, s.plan_id, s.status, s.billing_cycle, s.amount,
                s.current_period_start, s.current_period_end,
                s.user_email, s.user_full_name,
                p.name as plan_name, p.monthly_plan_cost
            FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.tenant_id = :tenant_id
                AND s.status IN ('active', 'expired', 'trialing')
            ORDER BY s.created_at DESC
            LIMIT 1
        """),
        {"tenant_id": tenant_id}
    ).fetchone()

    return result


def create_manual_payment(session, subscription_id: str, tenant_id: str, amount: Decimal,
                         payment_notes: str = "Manual bank transfer payment"):
    """Create a manual payment record for offline payment"""
    now = datetime.now(timezone.utc)

    # Generate manual reference
    manual_reference = f"manual_banktransfer_{subscription_id}_{now.strftime('%Y%m%d%H%M%S')}"

    payment_id = session.execute(
        text("""
            INSERT INTO payments (
                id, subscription_id, tenant_id, amount, currency,
                status, payment_method, transaction_type,
                paystack_reference, description,
                created_at, processed_at, gateway_response
            ) VALUES (
                gen_random_uuid()::text, :subscription_id, :tenant_id, :amount, 'NGN',
                'completed', 'bank_transfer', 'renewal',
                :reference, :description,
                :created_at, :processed_at, :gateway_response
            )
            RETURNING id
        """),
        {
            "subscription_id": subscription_id,
            "tenant_id": tenant_id,
            "amount": amount,
            "reference": manual_reference,
            "description": payment_notes,
            "created_at": now,
            "processed_at": now,
            "gateway_response": '{"payment_method": "manual_bank_transfer", "processed_by": "admin", "notes": "' + payment_notes + '"}'
        }
    ).fetchone()[0]

    return payment_id, manual_reference


def extend_subscription(session, subscription_id: str, extension_days: int = 30):
    """Extend subscription period by specified days"""
    now = datetime.now(timezone.utc)

    # Get current subscription details
    subscription = session.execute(
        text("""
            SELECT current_period_end, status
            FROM subscriptions
            WHERE id = :subscription_id
        """),
        {"subscription_id": subscription_id}
    ).fetchone()

    current_period_end = subscription[0]
    current_status = subscription[1]

    # Calculate new period
    if current_status == 'expired':
        # If expired, start from now
        new_period_start = now
        new_period_end = now + timedelta(days=extension_days)
    else:
        # If active/trialing, extend from current period end
        new_period_start = current_period_end
        new_period_end = current_period_end + timedelta(days=extension_days)

    # Update subscription
    session.execute(
        text("""
            UPDATE subscriptions
            SET
                current_period_start = :new_period_start,
                current_period_end = :new_period_end,
                ends_at = :new_period_end,
                status = 'active',
                updated_at = :updated_at
            WHERE id = :subscription_id
        """),
        {
            "subscription_id": subscription_id,
            "new_period_start": new_period_start,
            "new_period_end": new_period_end,
            "updated_at": now
        }
    )

    return new_period_start, new_period_end


def create_invoice(session, payment_id: str, subscription_id: str, tenant_id: str,
                  amount: Decimal, period_start: datetime, period_end: datetime):
    """Create invoice for the manual payment"""
    now = datetime.now(timezone.utc)

    # Get next invoice number
    last_invoice = session.execute(
        text("""
            SELECT invoice_number
            FROM invoices
            ORDER BY created_at DESC
            LIMIT 1
        """)
    ).fetchone()

    if last_invoice:
        # Extract number from INV-YYYYMMDD-XXXX format
        last_number = int(last_invoice[0].split('-')[-1])
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-{str(last_number + 1).zfill(4)}"
    else:
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-0001"

    invoice_id = session.execute(
        text("""
            INSERT INTO invoices (
                id, invoice_number, subscription_id, tenant_id,
                total_amount, currency, status,
                period_start, period_end,
                notes, created_at, paid_at, invoice_metadata
            ) VALUES (
                gen_random_uuid()::text, :invoice_number, :subscription_id, :tenant_id,
                :amount, 'NGN', 'completed',
                :period_start, :period_end,
                :notes, :created_at, :paid_at, :metadata
            )
            RETURNING id
        """),
        {
            "invoice_number": invoice_number,
            "subscription_id": subscription_id,
            "tenant_id": tenant_id,
            "amount": amount,
            "period_start": period_start,
            "period_end": period_end,
            "notes": "Manual payment - Bank Transfer",
            "created_at": now,
            "paid_at": now,
            "metadata": '{"payment_method": "bank_transfer", "manual_entry": true}'
        }
    ).fetchone()[0]

    # Link payment to invoice
    session.execute(
        text("""
            UPDATE payments
            SET invoice_id = :invoice_id
            WHERE id = :payment_id
        """),
        {"invoice_id": invoice_id, "payment_id": payment_id}
    )

    return invoice_id, invoice_number


def log_subscription_change(session, subscription_id: str, change_type: str, notes: str):
    """Log the subscription change in audit trail"""
    session.execute(
        text("""
            INSERT INTO subscription_changes (
                id, subscription_id, change_type,
                changed_at, change_reason, change_metadata
            ) VALUES (
                gen_random_uuid()::text, :subscription_id, :change_type,
                :changed_at, :reason, :metadata
            )
        """),
        {
            "subscription_id": subscription_id,
            "change_type": change_type,
            "changed_at": datetime.now(timezone.utc),
            "reason": notes,
            "metadata": '{"manual_entry": true, "payment_method": "bank_transfer"}'
        }
    )


def main():
    """Main execution"""
    print("=" * 80)
    print("Manual Subscription Extension for Offline Payments")
    print("=" * 80)

    if len(sys.argv) < 2:
        print("\nERROR: Tenant ID required")
        print("Usage: python manual_subscription_extension.py <tenant_id>")
        sys.exit(1)

    tenant_id = sys.argv[1]

    # Get payment details from user
    print(f"\nTenant ID: {tenant_id}")

    session = Session()

    try:
        # Get subscription
        subscription = get_tenant_subscription(session, tenant_id)

        if not subscription:
            print(f"\nERROR: No active subscription found for tenant {tenant_id}")
            sys.exit(1)

        subscription_id, plan_id, status, billing_cycle, current_amount, \
        period_start, period_end, user_email, user_name, plan_name, plan_cost = subscription

        print(f"\nSubscription Details:")
        print(f"  Subscription ID: {subscription_id}")
        print(f"  Plan: {plan_name}")
        print(f"  Status: {status}")
        print(f"  Billing Cycle: {billing_cycle}")
        print(f"  Current Period: {period_start.date()} to {period_end.date()}")
        print(f"  User: {user_name} ({user_email})")
        print(f"  Plan Cost: {plan_cost} NGN/month")

        # Get payment amount
        print(f"\nPayment Information:")
        payment_amount = Decimal(input(f"  Enter payment amount received (default: {plan_cost} NGN): ") or str(plan_cost))
        payment_notes = input("  Enter payment notes (optional): ") or "Manual bank transfer payment"

        # Get extension period
        extension_days = int(input("  Enter extension days (default: 30): ") or "30")

        print(f"\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Tenant ID: {tenant_id}")
        print(f"Subscription: {plan_name} ({billing_cycle})")
        print(f"Payment Amount: {payment_amount} NGN")
        print(f"Extension Period: {extension_days} days")
        print(f"Payment Notes: {payment_notes}")

        response = input(f"\nProceed with subscription extension? (yes/no): ")

        if response.lower() != 'yes':
            print("Operation cancelled.")
            return

        print(f"\nProcessing...")

        # 1. Create payment record
        payment_id, reference = create_manual_payment(
            session, subscription_id, tenant_id, payment_amount, payment_notes
        )
        print(f"✅ Payment created: {payment_id}")
        print(f"   Reference: {reference}")

        # 2. Extend subscription
        new_period_start, new_period_end = extend_subscription(
            session, subscription_id, extension_days
        )
        print(f"✅ Subscription extended")
        print(f"   New period: {new_period_start.date()} to {new_period_end.date()}")

        # 3. Create invoice
        invoice_id, invoice_number = create_invoice(
            session, payment_id, subscription_id, tenant_id,
            payment_amount, new_period_start, new_period_end
        )
        print(f"✅ Invoice created: {invoice_number}")

        # 4. Log change
        log_subscription_change(
            session, subscription_id, "manual_extension",
            f"Manual extension via bank transfer: {payment_notes}"
        )
        print(f"✅ Change logged in audit trail")

        # Commit all changes
        session.commit()

        print("\n" + "=" * 80)
        print("SUCCESS")
        print("=" * 80)
        print(f"Subscription extended successfully!")
        print(f"Payment ID: {payment_id}")
        print(f"Invoice Number: {invoice_number}")
        print(f"New expiration: {new_period_end.date()}")
        print(f"\nUser email: {user_email}")
        print(f"You may want to send a confirmation email to the customer.")
        print("=" * 80)

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
