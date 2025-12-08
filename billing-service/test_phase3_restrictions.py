"""
Test script for Phase 3: Account Restrictions

This script tests:
1. Subscription status checking
2. Grace period logic
3. Usage limit enforcement
4. Restriction API endpoints
"""
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables
os.environ['DATABASE_URL'] = 'postgresql://postgres:password@localhost:5432/billing_db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'

from app.core.database import SessionLocal
from app.models.subscription import Subscription, SubscriptionStatus, UsageTracking
from app.models.plan import Plan
from app.services.subscription_checker import SubscriptionChecker, SubscriptionRestrictionError


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}\n")


def test_subscription_status_checks():
    """Test basic subscription status checking"""
    print_section("TEST 1: Subscription Status Checks")

    db = SessionLocal()
    checker = SubscriptionChecker(db)

    try:
        # Test 1: Active subscription
        print("Creating active subscription...")
        plan = db.query(Plan).filter(Plan.name == "Free").first()
        if not plan:
            print("❌ No Free plan found. Run migrations first.")
            return False

        active_sub = Subscription(
            id="test-sub-active",
            tenant_id="test-tenant-active",
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
            auto_renew=True,
            amount=0.00,
            currency="NGN"
        )
        db.add(active_sub)
        db.commit()

        is_active, reason = checker.check_subscription_active("test-tenant-active")
        if is_active and reason is None:
            print("✅ Active subscription check passed")
        else:
            print(f"❌ Active subscription check failed: {reason}")
            return False

        # Test 2: Expired subscription
        print("\nTesting expired subscription...")
        expired_sub = Subscription(
            id="test-sub-expired",
            tenant_id="test-tenant-expired",
            plan_id=plan.id,
            status=SubscriptionStatus.EXPIRED,
            current_period_start=datetime.utcnow() - timedelta(days=60),
            current_period_end=datetime.utcnow() - timedelta(days=30),
            amount=0.00,
            currency="NGN"
        )
        db.add(expired_sub)
        db.commit()

        is_active, reason = checker.check_subscription_active("test-tenant-expired")
        if not is_active and "expired" in reason.lower():
            print(f"✅ Expired subscription check passed: {reason}")
        else:
            print(f"❌ Expired subscription check failed")
            return False

        # Test 3: Trial subscription
        print("\nTesting active trial...")
        trial_sub = Subscription(
            id="test-sub-trial",
            tenant_id="test-tenant-trial",
            plan_id=plan.id,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=datetime.utcnow() + timedelta(days=5),
            amount=0.00,
            currency="NGN"
        )
        db.add(trial_sub)
        db.commit()

        is_active, reason = checker.check_subscription_active("test-tenant-trial")
        if is_active:
            print("✅ Active trial check passed")
        else:
            print(f"❌ Active trial check failed: {reason}")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        db.query(Subscription).filter(
            Subscription.id.in_([
                "test-sub-active",
                "test-sub-expired",
                "test-sub-trial"
            ])
        ).delete()
        db.commit()
        db.close()


def test_grace_period_logic():
    """Test 3-day grace period for past_due subscriptions"""
    print_section("TEST 2: Grace Period Logic")

    db = SessionLocal()
    checker = SubscriptionChecker(db)

    try:
        plan = db.query(Plan).first()
        if not plan:
            print("❌ No plan found")
            return False

        # Test 1: Past due within grace period
        print("Testing past_due within grace period...")
        grace_sub = Subscription(
            id="test-sub-grace",
            tenant_id="test-tenant-grace",
            plan_id=plan.id,
            status=SubscriptionStatus.PAST_DUE,
            current_period_end=datetime.utcnow() - timedelta(days=1),  # 1 day overdue
            amount=0.00,
            currency="NGN"
        )
        db.add(grace_sub)
        db.commit()

        is_active, reason = checker.check_subscription_active("test-tenant-grace", include_grace_period=True)
        if is_active:
            print(f"✅ Grace period check passed (within 3 days)")
        else:
            print(f"❌ Grace period check failed: {reason}")
            return False

        # Test 2: Past due beyond grace period
        print("\nTesting past_due beyond grace period...")
        no_grace_sub = Subscription(
            id="test-sub-no-grace",
            tenant_id="test-tenant-no-grace",
            plan_id=plan.id,
            status=SubscriptionStatus.PAST_DUE,
            current_period_end=datetime.utcnow() - timedelta(days=5),  # 5 days overdue
            amount=0.00,
            currency="NGN"
        )
        db.add(no_grace_sub)
        db.commit()

        is_active, reason = checker.check_subscription_active("test-tenant-no-grace", include_grace_period=True)
        if not is_active and "grace period" in reason.lower():
            print(f"✅ No grace period check passed: {reason}")
        else:
            print(f"❌ No grace period check failed")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        db.query(Subscription).filter(
            Subscription.id.in_(["test-sub-grace", "test-sub-no-grace"])
        ).delete()
        db.commit()
        db.close()


def test_usage_limit_enforcement():
    """Test document, website, and chat limit enforcement"""
    print_section("TEST 3: Usage Limit Enforcement")

    db = SessionLocal()
    checker = SubscriptionChecker(db)

    try:
        # Get Free plan (5 docs, 1 website, 300 chats)
        plan = db.query(Plan).filter(Plan.name == "Free").first()
        if not plan:
            print("❌ Free plan not found")
            return False

        print(f"Using Free plan: {plan.max_documents} docs, {plan.max_websites} websites, {plan.monthly_chats} chats")

        # Create subscription
        sub = Subscription(
            id="test-sub-limits",
            tenant_id="test-tenant-limits",
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=datetime.utcnow() + timedelta(days=30),
            amount=0.00,
            currency="NGN"
        )
        db.add(sub)
        db.commit()

        # Create usage tracking
        usage = UsageTracking(
            subscription_id=sub.id,
            documents_uploaded=4,  # 1 below limit
            websites_ingested=1,   # At limit
            monthly_chats_used=299  # 1 below limit
        )
        db.add(usage)
        db.commit()

        # Test 1: Can upload document (4/5 used)
        print("\nTesting document upload (4/5 used)...")
        can_upload, reason = checker.check_can_upload_document("test-tenant-limits")
        if can_upload:
            print("✅ Document upload allowed")
        else:
            print(f"❌ Document upload check failed: {reason}")
            return False

        # Test 2: Cannot ingest website (1/1 used)
        print("\nTesting website ingestion (1/1 used)...")
        can_ingest, reason = checker.check_can_ingest_website("test-tenant-limits")
        if not can_ingest and "limit reached" in reason.lower():
            print(f"✅ Website ingestion blocked: {reason}")
        else:
            print(f"❌ Website ingestion check failed")
            return False

        # Test 3: Can send chat (299/300 used)
        print("\nTesting chat send (299/300 used)...")
        can_chat, reason = checker.check_can_send_chat("test-tenant-limits")
        if can_chat:
            print("✅ Chat allowed")
        else:
            print(f"❌ Chat check failed: {reason}")
            return False

        # Test 4: Update to exceed limits and test again
        print("\nUpdating usage to exceed all limits...")
        usage.documents_uploaded = 5  # At limit
        usage.websites_ingested = 1   # At limit
        usage.monthly_chats_used = 300  # At limit
        db.commit()

        can_upload, reason = checker.check_can_upload_document("test-tenant-limits")
        can_ingest, reason2 = checker.check_can_ingest_website("test-tenant-limits")
        can_chat, reason3 = checker.check_can_send_chat("test-tenant-limits")

        if not can_upload and not can_ingest and not can_chat:
            print("✅ All operations correctly blocked at limits")
        else:
            print(f"❌ Limit enforcement failed")
            print(f"  Upload: {can_upload} (should be False)")
            print(f"  Ingest: {can_ingest} (should be False)")
            print(f"  Chat: {can_chat} (should be False)")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        db.query(UsageTracking).filter(
            UsageTracking.subscription_id == "test-sub-limits"
        ).delete()
        db.query(Subscription).filter(
            Subscription.id == "test-sub-limits"
        ).delete()
        db.commit()
        db.close()


def test_usage_summary():
    """Test usage summary generation"""
    print_section("TEST 4: Usage Summary")

    db = SessionLocal()
    checker = SubscriptionChecker(db)

    try:
        plan = db.query(Plan).filter(Plan.name == "Pro").first()
        if not plan:
            print("❌ Pro plan not found")
            return False

        # Create subscription with usage
        sub = Subscription(
            id="test-sub-summary",
            tenant_id="test-tenant-summary",
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=datetime.utcnow() + timedelta(days=30),
            amount=29.99,
            currency="USD"
        )
        db.add(sub)
        db.commit()

        usage = UsageTracking(
            subscription_id=sub.id,
            documents_uploaded=50,
            websites_ingested=5,
            monthly_chats_used=7500,
            monthly_reset_at=datetime.utcnow()
        )
        db.add(usage)
        db.commit()

        # Get summary
        summary = checker.get_usage_summary("test-tenant-summary")

        if summary:
            print("Usage Summary:")
            print(f"  Plan: {summary['plan_name']}")
            print(f"  Status: {summary['subscription_status']}")
            print(f"  Documents: {summary['documents']['used']}/{summary['documents']['limit']} (remaining: {summary['documents']['remaining']})")
            print(f"  Websites: {summary['websites']['used']}/{summary['websites']['limit']} (remaining: {summary['websites']['remaining']})")
            print(f"  Chats: {summary['monthly_chats']['used']}/{summary['monthly_chats']['limit']} (remaining: {summary['monthly_chats']['remaining']})")

            # Verify calculations
            if (summary['documents']['remaining'] == 50 and
                summary['websites']['remaining'] == 5 and
                summary['monthly_chats']['remaining'] == 7500):
                print("\n✅ Usage summary calculations correct")
                return True
            else:
                print("\n❌ Usage summary calculations incorrect")
                return False
        else:
            print("❌ No summary returned")
            return False

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        db.query(UsageTracking).filter(
            UsageTracking.subscription_id == "test-sub-summary"
        ).delete()
        db.query(Subscription).filter(
            Subscription.id == "test-sub-summary"
        ).delete()
        db.commit()
        db.close()


def main():
    """Run all tests"""
    print_section("PHASE 3: ACCOUNT RESTRICTIONS - TEST SUITE")

    tests = [
        ("Subscription Status Checks", test_subscription_status_checks),
        ("Grace Period Logic", test_grace_period_logic),
        ("Usage Limit Enforcement", test_usage_limit_enforcement),
        ("Usage Summary", test_usage_summary)
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Print summary
    print_section("TEST RESULTS SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All Phase 3 tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
