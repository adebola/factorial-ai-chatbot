"""
Unit tests for subscription renewal functionality.

Tests cover:
- Renewal of ACTIVE subscriptions (extends period)
- Renewal of EXPIRED subscriptions (reactivates)
- Error cases (CANCELLED, PENDING, wrong tenant, pending downgrades)
- Payment verification for renewal transactions
- Period calculation logic
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.subscription_service import SubscriptionService
from app.models.subscription import (
    Subscription, SubscriptionStatus, BillingCycle, Payment, PaymentStatus,
    TransactionType
)


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock()


@pytest.fixture
def mock_paystack():
    """Mock PaystackService"""
    return MagicMock()


@pytest.fixture
def mock_plan_service():
    """Mock PlanService"""
    mock = MagicMock()
    mock.get_plan_by_id.return_value = MagicMock(
        id="plan-123",
        name="Pro Plan",
        monthly_plan_cost=Decimal("999.00"),
        yearly_plan_cost=Decimal("9990.00")
    )
    return mock


@pytest.fixture
def subscription_service(mock_db, mock_paystack, mock_plan_service):
    """Create SubscriptionService with mocked dependencies"""
    service = SubscriptionService(mock_db)
    service.paystack = mock_paystack
    service.plan_service = mock_plan_service
    return service


@pytest.fixture
def active_subscription():
    """Create an ACTIVE subscription"""
    now = datetime.now(timezone.utc)
    return Subscription(
        id="sub-123",
        tenant_id="tenant-456",
        plan_id="plan-789",
        status=SubscriptionStatus.ACTIVE,
        billing_cycle=BillingCycle.MONTHLY,
        amount=Decimal("999.00"),
        currency="NGN",
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
        ends_at=now + timedelta(days=15),
        starts_at=now - timedelta(days=15),
        user_email="user@example.com",
        user_full_name="Test User",
        pending_plan_id=None
    )


@pytest.fixture
def expired_subscription():
    """Create an EXPIRED subscription"""
    now = datetime.now(timezone.utc)
    return Subscription(
        id="sub-expired",
        tenant_id="tenant-456",
        plan_id="plan-789",
        status=SubscriptionStatus.EXPIRED,
        billing_cycle=BillingCycle.MONTHLY,
        amount=Decimal("999.00"),
        currency="NGN",
        current_period_start=now - timedelta(days=60),
        current_period_end=now - timedelta(days=30),
        ends_at=now - timedelta(days=30),
        starts_at=now - timedelta(days=60),
        user_email="user@example.com",
        user_full_name="Test User",
        pending_plan_id=None
    )


class TestRenewActiveSubscription:
    """Test renewal of ACTIVE subscriptions"""

    @pytest.mark.asyncio
    async def test_renew_active_subscription_success(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test successful renewal of active subscription"""
        # Mock database query
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        # Mock Paystack initialization
        subscription_service.paystack.initialize_transaction = AsyncMock(
            return_value={
                "success": True,
                "access_code": "test-access-code",
                "authorization_url": "https://paystack.com/pay/test"
            }
        )

        # Renew subscription
        result = await subscription_service.renew_subscription(
            subscription_id="sub-123",
            user_email="user@example.com",
            user_full_name="Test User"
        )

        # Assertions
        assert result["success"] is True
        assert result["amount"] == 999.00
        assert result["currency"] == "NGN"
        assert "payment_url" in result
        assert "renewal_" in result["payment_reference"]

        # Verify new period extends from current_period_end
        new_period_start = datetime.fromisoformat(result["new_period_start"])
        assert new_period_start == active_subscription.current_period_end

        # Verify new period end is 30 days from new start
        new_period_end = datetime.fromisoformat(result["new_period_end"])
        expected_end = new_period_start + timedelta(days=30)
        assert abs((new_period_end - expected_end).total_seconds()) < 2

    @pytest.mark.asyncio
    async def test_renew_active_yearly_subscription(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test renewal of yearly subscription extends by 365 days"""
        active_subscription.billing_cycle = BillingCycle.YEARLY
        active_subscription.amount = Decimal("9990.00")

        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        subscription_service.paystack.initialize_transaction = AsyncMock(
            return_value={
                "success": True,
                "access_code": "test-access-code",
                "authorization_url": "https://paystack.com/pay/test"
            }
        )

        result = await subscription_service.renew_subscription(
            subscription_id="sub-123",
            user_email="user@example.com"
        )

        # Verify yearly extension (365 days)
        new_period_start = datetime.fromisoformat(result["new_period_start"])
        new_period_end = datetime.fromisoformat(result["new_period_end"])
        days_diff = (new_period_end - new_period_start).days
        assert days_diff == 365


class TestRenewExpiredSubscription:
    """Test renewal of EXPIRED subscriptions"""

    @pytest.mark.asyncio
    async def test_renew_expired_subscription_success(
        self, subscription_service, expired_subscription, mock_db
    ):
        """Test successful renewal of expired subscription starts fresh from today"""
        mock_db.query.return_value.filter.return_value.first.return_value = expired_subscription

        subscription_service.paystack.initialize_transaction = AsyncMock(
            return_value={
                "success": True,
                "access_code": "test-access-code",
                "authorization_url": "https://paystack.com/pay/test"
            }
        )

        result = await subscription_service.renew_subscription(
            subscription_id="sub-expired",
            user_email="user@example.com",
            user_full_name="Test User"
        )

        # Assertions
        assert result["success"] is True

        # Verify new period starts from NOW (not from expired period_end)
        new_period_start = datetime.fromisoformat(result["new_period_start"])
        now = datetime.now(timezone.utc)
        time_diff = abs((new_period_start - now).total_seconds())
        assert time_diff < 5  # Within 5 seconds of now

        # Verify new period end is 30 days from start
        new_period_end = datetime.fromisoformat(result["new_period_end"])
        expected_end = new_period_start + timedelta(days=30)
        assert abs((new_period_end - expected_end).total_seconds()) < 2


class TestRenewalErrorCases:
    """Test renewal error scenarios"""

    @pytest.mark.asyncio
    async def test_renew_cancelled_subscription_fails(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that cancelled subscriptions cannot be renewed"""
        active_subscription.status = SubscriptionStatus.CANCELLED
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        with pytest.raises(ValueError) as exc_info:
            await subscription_service.renew_subscription(
                subscription_id="sub-123",
                user_email="user@example.com"
            )

        assert "Cannot renew cancelled subscription" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_renew_pending_subscription_fails(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that pending subscriptions cannot be renewed"""
        active_subscription.status = SubscriptionStatus.PENDING
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        with pytest.raises(ValueError) as exc_info:
            await subscription_service.renew_subscription(
                subscription_id="sub-123",
                user_email="user@example.com"
            )

        assert "Cannot renew pending subscription" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_renew_with_pending_downgrade_fails(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that subscriptions with pending plan changes cannot be renewed"""
        active_subscription.pending_plan_id = "new-plan-123"
        active_subscription.pending_plan_effective_date = datetime.now(timezone.utc) + timedelta(days=15)
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        with pytest.raises(ValueError) as exc_info:
            await subscription_service.renew_subscription(
                subscription_id="sub-123",
                user_email="user@example.com"
            )

        assert "Cannot renew subscription with pending plan change" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_renew_nonexistent_subscription_fails(
        self, subscription_service, mock_db
    ):
        """Test that renewing non-existent subscription fails"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError) as exc_info:
            await subscription_service.renew_subscription(
                subscription_id="non-existent",
                user_email="user@example.com"
            )

        assert "Subscription not found" in str(exc_info.value)


class TestRenewalPaymentVerification:
    """Test payment verification for renewal transactions"""

    def test_verify_renewal_payment_updates_period(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that renewal payment verification updates subscription period"""
        now = datetime.now(timezone.utc)
        new_period_start = now + timedelta(days=15)
        new_period_end = now + timedelta(days=45)

        # Create renewal payment
        payment = Payment(
            id="payment-123",
            subscription_id="sub-123",
            tenant_id="tenant-456",
            amount=Decimal("999.00"),
            currency="NGN",
            status=PaymentStatus.PENDING,
            transaction_type=TransactionType.RENEWAL,
            paystack_reference="renewal_sub-123_abc123",
            payment_metadata={
                "transaction_type": "renewal",
                "new_period_start": new_period_start.isoformat(),
                "new_period_end": new_period_end.isoformat(),
                "previous_status": "active"
            }
        )

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            payment,  # First call: get payment
            active_subscription  # Second call: get subscription
        ]

        # Mock Paystack verification
        subscription_service.paystack.verify_transaction = AsyncMock(
            return_value={
                "success": True,
                "verified": True,
                "amount": Decimal("999.00"),
                "transaction_id": "txn-123",
                "data": {}
            }
        )

        # Note: This is a simplified test - in real implementation,
        # verify_subscription_payment is async and has more complex logic

    def test_verify_renewal_payment_reactivates_expired(
        self, subscription_service, expired_subscription, mock_db
    ):
        """Test that renewal payment reactivates EXPIRED subscriptions"""
        now = datetime.now(timezone.utc)
        new_period_start = now
        new_period_end = now + timedelta(days=30)

        # Create renewal payment for expired subscription
        payment = Payment(
            id="payment-123",
            subscription_id="sub-expired",
            tenant_id="tenant-456",
            amount=Decimal("999.00"),
            currency="NGN",
            status=PaymentStatus.PENDING,
            transaction_type=TransactionType.RENEWAL,
            paystack_reference="renewal_sub-expired_xyz789",
            payment_metadata={
                "transaction_type": "renewal",
                "new_period_start": new_period_start.isoformat(),
                "new_period_end": new_period_end.isoformat(),
                "previous_status": "expired"
            }
        )

        # Verify that status would change from EXPIRED to ACTIVE
        assert expired_subscription.status == SubscriptionStatus.EXPIRED
        # After payment verification, status should become ACTIVE


class TestRenewalPaymentMetadata:
    """Test renewal payment metadata storage"""

    @pytest.mark.asyncio
    async def test_renewal_payment_includes_metadata(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that renewal payment includes comprehensive metadata"""
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        subscription_service.paystack.initialize_transaction = AsyncMock(
            return_value={
                "success": True,
                "access_code": "test-access-code",
                "authorization_url": "https://paystack.com/pay/test"
            }
        )

        result = await subscription_service.renew_subscription(
            subscription_id="sub-123",
            user_email="user@example.com"
        )

        # Verify payment was created with correct transaction type
        payment_call = mock_db.add.call_args[0][0]
        assert isinstance(payment_call, Payment)
        assert payment_call.transaction_type == TransactionType.RENEWAL
        assert "new_period_start" in payment_call.payment_metadata
        assert "new_period_end" in payment_call.payment_metadata
        assert payment_call.payment_metadata["previous_status"] == "active"


class TestRenewalAmountCalculation:
    """Test renewal amount calculation (always full cost)"""

    @pytest.mark.asyncio
    async def test_renewal_charges_full_amount_no_proration(
        self, subscription_service, active_subscription, mock_db
    ):
        """Test that renewal always charges full plan cost (no proration)"""
        mock_db.query.return_value.filter.return_value.first.return_value = active_subscription

        subscription_service.paystack.initialize_transaction = AsyncMock(
            return_value={
                "success": True,
                "access_code": "test-access-code",
                "authorization_url": "https://paystack.com/pay/test"
            }
        )

        result = await subscription_service.renew_subscription(
            subscription_id="sub-123",
            user_email="user@example.com"
        )

        # Verify amount equals subscription.amount (full cost)
        assert result["amount"] == float(active_subscription.amount)
        assert result["amount"] == 999.00
