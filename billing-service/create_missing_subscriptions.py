"""
Create default trial subscriptions for tenants that don't have any subscription.

This script:
1. Finds all tenants (from authorization_db2) without subscriptions (in billing_db)
2. Creates a 14-day trial subscription for each tenant
3. Sets subscription status based on trial expiration (TRIALING or EXPIRED)
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Database connections
BILLING_DB_URL = "postgresql://postgres:password@localhost:5432/billing_db"
AUTH_DB_URL = "postgresql://postgres:password@localhost:5432/authorization_db2"

print(f"Connecting to databases...")
billing_engine = create_engine(BILLING_DB_URL)
auth_engine = create_engine(AUTH_DB_URL)

BillingSession = sessionmaker(bind=billing_engine)
AuthSession = sessionmaker(bind=auth_engine)


def get_default_plan_id(billing_session):
    """Get the default plan ID (cheapest active plan)"""
    result = billing_session.execute(
        text("""
            SELECT id, name, monthly_plan_cost
            FROM plans
            WHERE is_active = true
            ORDER BY monthly_plan_cost ASC
            LIMIT 1
        """)
    ).fetchone()

    if not result:
        print("ERROR: No active plans found in database")
        return None

    print(f"Found default plan: {result[1]} (ID: {result[0]}, Cost: ${result[2]}/month)")
    return result[0]


def get_tenants_without_subscriptions(auth_session, billing_session):
    """Get all tenants that don't have any subscription"""
    # Get all tenant IDs from billing subscriptions
    subscription_tenant_ids = billing_session.execute(
        text("SELECT DISTINCT tenant_id FROM subscriptions")
    ).fetchall()
    subscription_tenant_ids = {row[0] for row in subscription_tenant_ids}

    # Get all tenants from auth database
    tenants = auth_session.execute(
        text("""
            SELECT id, name, domain, created_at
            FROM tenants
            WHERE is_active = true
            ORDER BY created_at
        """)
    ).fetchall()

    # Filter tenants without subscriptions
    tenants_without_subs = [
        tenant for tenant in tenants
        if tenant[0] not in subscription_tenant_ids
    ]

    print(f"\nTotal tenants: {len(tenants)}")
    print(f"Tenants with subscriptions: {len(subscription_tenant_ids)}")
    print(f"Tenants WITHOUT subscriptions: {len(tenants_without_subs)}")

    return tenants_without_subs


def create_trial_subscription(billing_session, tenant_id, tenant_created_at, plan_id):
    """Create a trial subscription for a tenant"""
    now = datetime.now(timezone.utc)

    # Ensure tenant_created_at is timezone-aware
    if tenant_created_at.tzinfo is None:
        tenant_created_at = tenant_created_at.replace(tzinfo=timezone.utc)

    # Trial starts when tenant was created
    trial_starts_at = tenant_created_at
    trial_ends_at = tenant_created_at + timedelta(days=14)

    # Subscription period same as trial period
    starts_at = trial_starts_at
    ends_at = trial_ends_at
    current_period_start = trial_starts_at
    current_period_end = trial_ends_at

    # Determine status based on whether trial has expired
    if trial_ends_at < now:
        status = 'expired'
        print(f"  - Trial expired on {trial_ends_at.date()} (setting status to EXPIRED)")
    else:
        status = 'trialing'
        print(f"  - Trial expires on {trial_ends_at.date()} (setting status to TRIALING)")

    # Create subscription
    insert_query = text("""
        INSERT INTO subscriptions (
            id, tenant_id, plan_id, status, billing_cycle,
            amount, currency,
            starts_at, ends_at,
            current_period_start, current_period_end,
            trial_starts_at, trial_ends_at,
            auto_renew, cancel_at_period_end, subscription_metadata,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid()::text, :tenant_id, :plan_id, :status, 'monthly',
            0.00, 'NGN',
            :starts_at, :ends_at,
            :current_period_start, :current_period_end,
            :trial_starts_at, :trial_ends_at,
            true, false, '{}'::jsonb,
            :created_at, :updated_at
        )
        RETURNING id
    """)

    result = billing_session.execute(insert_query, {
        'tenant_id': tenant_id,
        'plan_id': plan_id,
        'status': status,
        'starts_at': starts_at,
        'ends_at': ends_at,
        'current_period_start': current_period_start,
        'current_period_end': current_period_end,
        'trial_starts_at': trial_starts_at,
        'trial_ends_at': trial_ends_at,
        'created_at': tenant_created_at,
        'updated_at': now
    })

    subscription_id = result.fetchone()[0]
    return subscription_id, status


def main():
    """Main execution"""
    print("=" * 80)
    print("Creating Default Trial Subscriptions for Tenants")
    print("=" * 80)

    billing_session = BillingSession()
    auth_session = AuthSession()

    try:
        # Get default plan
        default_plan_id = get_default_plan_id(billing_session)
        if not default_plan_id:
            return

        # Get tenants without subscriptions
        tenants = get_tenants_without_subscriptions(auth_session, billing_session)

        if not tenants:
            print("\nNo tenants without subscriptions found. All done!")
            return

        # Show tenants
        print("\nTenants without subscriptions:")
        print("-" * 80)
        for tenant in tenants:
            tenant_id, name, domain, created_at = tenant
            print(f"- {name} ({domain}) - Created: {created_at.date() if created_at else 'Unknown'}")

        print("\n" + "=" * 80)
        response = input(f"\nCreate trial subscriptions for {len(tenants)} tenants? (yes/no): ")

        if response.lower() != 'yes':
            print("Operation cancelled.")
            return

        # Create subscriptions
        print("\nCreating subscriptions...")
        print("-" * 80)

        created_count = 0
        expired_count = 0
        trialing_count = 0

        for tenant in tenants:
            tenant_id, name, domain, created_at = tenant
            print(f"\nTenant: {name} ({domain})")
            print(f"  Created: {created_at if created_at else 'Unknown'}")

            try:
                subscription_id, status = create_trial_subscription(
                    billing_session, tenant_id, created_at or datetime.now(timezone.utc), default_plan_id
                )
                billing_session.commit()

                print(f"  ✅ Created subscription: {subscription_id}")
                created_count += 1

                if status == 'expired':
                    expired_count += 1
                else:
                    trialing_count += 1

            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
                billing_session.rollback()

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total tenants processed: {len(tenants)}")
        print(f"Subscriptions created: {created_count}")
        print(f"  - TRIALING (active): {trialing_count}")
        print(f"  - EXPIRED: {expired_count}")
        print("=" * 80)

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        billing_session.rollback()
        raise
    finally:
        billing_session.close()
        auth_session.close()


if __name__ == "__main__":
    main()
