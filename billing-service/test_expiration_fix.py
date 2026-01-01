"""
Test script to verify subscription expiration status fix.

This script tests:
1. Real-time status check in /current endpoint
2. Scheduled job logic (without auto_renew filter)
"""

import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.subscription import Subscription, SubscriptionStatus
from app.services.subscription_service import SubscriptionService

# Database connection
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/workflow_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def test_real_time_status_check():
    """Test real-time status checking"""
    print("\n" + "=" * 70)
    print("TEST 1: Real-time Status Check")
    print("=" * 70)

    db = SessionLocal()

    try:
        # Find subscription 8fca619b-31e6-42d8-93eb-a71150449a5b
        subscription_id = "8fca619b-31e6-42d8-93eb-a71150449a5b"
        subscription = db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not subscription:
            print(f"❌ Subscription {subscription_id} not found")
            return

        print(f"\n📋 Subscription: {subscription.id}")
        print(f"   Tenant: {subscription.tenant_id}")
        print(f"   Status (before): {subscription.status.value}")
        print(f"   Period End: {subscription.current_period_end}")
        print(f"   Auto-Renew: {subscription.auto_renew}")

        now = datetime.now(timezone.utc)
        print(f"   Current Time: {now}")

        if subscription.current_period_end < now:
            print(f"   ⚠️  Subscription expired {(now - subscription.current_period_end).days} days ago")
        else:
            print(f"   ✅ Subscription expires in {(subscription.current_period_end - now).days} days")

        # Test real-time status check
        subscription_service = SubscriptionService(db)
        updated_subscription = subscription_service.check_and_update_subscription_status(subscription)

        print(f"\n   Status (after): {updated_subscription.status.value}")

        if updated_subscription.status == SubscriptionStatus.EXPIRED:
            print(f"   ✅ Status correctly updated to EXPIRED")
        else:
            print(f"   ❌ Status should be EXPIRED but is {updated_subscription.status.value}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


def test_scheduled_job_logic():
    """Test that scheduled job finds expired subscriptions (including auto_renew=True)"""
    print("\n" + "=" * 70)
    print("TEST 2: Scheduled Job Logic (No auto_renew Filter)")
    print("=" * 70)

    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        # Query logic matching the FIXED scheduled job
        expired_subscriptions = db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.current_period_end < now,
                Subscription.user_email.isnot(None)
            )
        ).all()

        print(f"\n📊 Found {len(expired_subscriptions)} expired ACTIVE subscriptions")
        print(f"   (Including auto_renew = True and False)\n")

        for sub in expired_subscriptions[:5]:  # Show first 5
            days_expired = (now - sub.current_period_end).days
            print(f"   • {sub.id[:8]}... | auto_renew={sub.auto_renew} | expired {days_expired} days ago")

        # Check for the specific subscription
        target_sub = next(
            (s for s in expired_subscriptions if s.id == "8fca619b-31e6-42d8-93eb-a71150449a5b"),
            None
        )

        if target_sub:
            print(f"\n   ✅ Target subscription {target_sub.id[:8]}... found in expired list")
            print(f"      auto_renew = {target_sub.auto_renew} (should now be included!)")
        else:
            print(f"\n   ⚠️  Target subscription NOT in expired list (may already be EXPIRED status)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


def test_api_endpoint_simulation():
    """Simulate what the /current endpoint will return"""
    print("\n" + "=" * 70)
    print("TEST 3: /current Endpoint Simulation")
    print("=" * 70)

    db = SessionLocal()

    try:
        subscription_service = SubscriptionService(db)

        # Get subscription by tenant
        tenant_id = "a8d86f80-a4cc-40a6-8e25-b87dba3aad51"
        subscription = subscription_service.get_subscription_by_tenant(tenant_id)

        if not subscription:
            print(f"❌ No subscription found for tenant {tenant_id}")
            return

        print(f"\n📋 Before real-time check:")
        print(f"   Status: {subscription.status.value}")
        print(f"   Period End: {subscription.current_period_end}")

        # Apply real-time status check (as the endpoint now does)
        subscription = subscription_service.check_and_update_subscription_status(subscription)

        print(f"\n📋 After real-time check (what API returns):")
        print(f"   Status: {subscription.status.value}")

        if subscription.status == SubscriptionStatus.EXPIRED:
            print(f"   ✅ API will now correctly return status='expired'")
        else:
            print(f"   Status: {subscription.status.value}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("SUBSCRIPTION EXPIRATION FIX - VERIFICATION TESTS")
    print("=" * 70)

    test_real_time_status_check()
    test_scheduled_job_logic()
    test_api_endpoint_simulation()

    print("\n" + "=" * 70)
    print("✅ Tests Complete")
    print("=" * 70)
    print("\nNext Steps:")
    print("1. Restart billing service to load updated code")
    print("2. Call GET /api/v1/subscriptions/current")
    print("3. Status should now show 'expired' instead of 'active'")
    print("=" * 70 + "\n")
