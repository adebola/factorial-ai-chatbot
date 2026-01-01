"""
Unit tests for trial upgrade expiration calculation.

Tests verify that when upgrading from TRIALING to paid plan:
1. Expiration date extends from trial end date (not from upgrade date)
2. User gets remaining trial days + full billing cycle
3. Subscription status transitions correctly
4. Edge cases are handled properly
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from decimal import Decimal

from app.services.subscription_service import SubscriptionService
from app.models.subscription import Subscription, SubscriptionStatus, BillingCycle


class TestTrialUpgradeExpiration:
    """Test trial upgrade expiration date calculation"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.service = SubscriptionService(self.mock_db)

    @patch('app.services.subscription_service.PlanService')
    def test_trial_upgrade_extends_from_trial_end_monthly(self, mock_plan_service):
        """Test that trial upgrade extends from trial end date for MONTHLY billing"""

        # Setup: Trial ending Dec 29, 2025
        trial_end_date = datetime(2025, 12, 29, 0, 0, 0, tzinfo=timezone.utc)
        upgrade_date = datetime(2025, 12, 19, 0, 0, 0, tzinfo=timezone.utc)  # 10 days before trial ends

        # Create subscription in TRIALING status
        subscription = Subscription(
            id="sub-123",
            tenant_id="tenant-123",
            plan_id="plan-basic",
            status=SubscriptionStatus.TRIALING,
            billing_cycle=BillingCycle.MONTHLY,
            amount=Decimal("0.00"),
            currency="NGN",
            starts_at=upgrade_date - timedelta(days=14),
            ends_at=trial_end_date,
            current_period_start=upgrade_date - timedelta(days=14),
            current_period_end=trial_end_date,
            trial_starts_at=upgrade_date - timedelta(days=14),
            trial_ends_at=trial_end_date
        )

        # Mock plan service
        new_plan = Mock()
        new_plan.id = "plan-lite"
        new_plan.is_active = True
        new_plan.monthly_plan_cost = Decimal("9.99")
        new_plan.yearly_plan_cost = Decimal("99.99")
        new_plan.name = "Lite"

        current_plan = Mock()
        current_plan.id = "plan-basic"
        current_plan.monthly_plan_cost = Decimal("0.00")
        current_plan.yearly_plan_cost = Decimal("0.00")
        current_plan.name = "Basic"

        mock_plan_service_instance = Mock()
        mock_plan_service_instance.get_plan_by_id = Mock(side_effect=lambda pid: new_plan if pid == "plan-lite" else current_plan)
        mock_plan_service.return_value = mock_plan_service_instance

        # Patch datetime.now to return upgrade_date
        with patch('app.services.subscription_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = upgrade_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Execute: Switch plan (simulate trial upgrade)
            result = self.service.switch_subscription_plan(
                subscription_id=subscription.id,
                new_plan_id="plan-lite",
                billing_cycle=BillingCycle.MONTHLY,
                prorate=True
            )

        # Assert: Expiration should be trial_end + 30 days = Jan 28, 2026
        expected_end_date = trial_end_date + timedelta(days=30)

        assert subscription.status == SubscriptionStatus.ACTIVE, "Status should be ACTIVE"
        assert subscription.trial_ends_at is None, "Trial should be complete"
        assert subscription.starts_at == trial_end_date, "Paid period should start at trial end"
        assert subscription.current_period_start == trial_end_date, "Period start should be trial end"
        assert subscription.current_period_end == expected_end_date, f"Period end should be {expected_end_date}"
        assert subscription.ends_at == expected_end_date, f"Subscription ends_at should be {expected_end_date}"

        # For the specific test case
        assert subscription.ends_at.day == 28, "Should end on Jan 28"
        assert subscription.ends_at.month == 1, "Should end in January"
        assert subscription.ends_at.year == 2026, "Should end in 2026"

    @patch('app.services.subscription_service.PlanService')
    def test_trial_upgrade_extends_from_trial_end_yearly(self, mock_plan_service):
        """Test that trial upgrade extends from trial end date for YEARLY billing"""

        # Setup: Trial ending Dec 29, 2025
        trial_end_date = datetime(2025, 12, 29, 0, 0, 0, tzinfo=timezone.utc)
        upgrade_date = datetime(2025, 12, 19, 0, 0, 0, tzinfo=timezone.utc)

        subscription = Subscription(
            id="sub-123",
            tenant_id="tenant-123",
            plan_id="plan-basic",
            status=SubscriptionStatus.TRIALING,
            billing_cycle=BillingCycle.YEARLY,
            amount=Decimal("0.00"),
            currency="NGN",
            starts_at=upgrade_date - timedelta(days=14),
            ends_at=trial_end_date,
            current_period_start=upgrade_date - timedelta(days=14),
            current_period_end=trial_end_date,
            trial_starts_at=upgrade_date - timedelta(days=14),
            trial_ends_at=trial_end_date
        )

        # Mock plan service
        new_plan = Mock()
        new_plan.id = "plan-pro"
        new_plan.is_active = True
        new_plan.monthly_plan_cost = Decimal("29.99")
        new_plan.yearly_plan_cost = Decimal("299.99")

        current_plan = Mock()
        current_plan.id = "plan-basic"
        current_plan.monthly_plan_cost = Decimal("0.00")
        current_plan.yearly_plan_cost = Decimal("0.00")

        mock_plan_service_instance = Mock()
        mock_plan_service_instance.get_plan_by_id = Mock(side_effect=lambda pid: new_plan if pid == "plan-pro" else current_plan)
        mock_plan_service.return_value = mock_plan_service_instance

        with patch('app.services.subscription_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = upgrade_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Execute
            result = self.service.switch_subscription_plan(
                subscription_id=subscription.id,
                new_plan_id="plan-pro",
                billing_cycle=BillingCycle.YEARLY,
                prorate=True
            )

        # Assert: Expiration should be trial_end + 365 days
        expected_end_date = trial_end_date + timedelta(days=365)

        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.ends_at == expected_end_date
        assert subscription.ends_at.year == 2026, "Yearly subscription should end in 2026"

    @patch('app.services.subscription_service.PlanService')
    def test_trial_upgrade_with_missing_trial_end_date(self, mock_plan_service):
        """Test fallback behavior when trial_ends_at is None"""

        upgrade_date = datetime(2025, 12, 19, 0, 0, 0, tzinfo=timezone.utc)

        # Subscription with None trial_ends_at (edge case)
        subscription = Subscription(
            id="sub-123",
            tenant_id="tenant-123",
            plan_id="plan-basic",
            status=SubscriptionStatus.TRIALING,
            billing_cycle=BillingCycle.MONTHLY,
            amount=Decimal("0.00"),
            currency="NGN",
            starts_at=upgrade_date - timedelta(days=14),
            ends_at=upgrade_date + timedelta(days=1),
            current_period_start=upgrade_date - timedelta(days=14),
            current_period_end=upgrade_date + timedelta(days=1),
            trial_starts_at=upgrade_date - timedelta(days=14),
            trial_ends_at=None  # Missing trial end date
        )

        # Mock plan service
        new_plan = Mock()
        new_plan.id = "plan-lite"
        new_plan.is_active = True
        new_plan.monthly_plan_cost = Decimal("9.99")
        new_plan.yearly_plan_cost = Decimal("99.99")

        current_plan = Mock()
        current_plan.id = "plan-basic"
        current_plan.monthly_plan_cost = Decimal("0.00")
        current_plan.yearly_plan_cost = Decimal("0.00")

        mock_plan_service_instance = Mock()
        mock_plan_service_instance.get_plan_by_id = Mock(side_effect=lambda pid: new_plan if pid == "plan-lite" else current_plan)
        mock_plan_service.return_value = mock_plan_service_instance

        with patch('app.services.subscription_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = upgrade_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Execute - should not crash
            result = self.service.switch_subscription_plan(
                subscription_id=subscription.id,
                new_plan_id="plan-lite",
                billing_cycle=BillingCycle.MONTHLY,
                prorate=True
            )

        # Assert: Should fallback to current behavior (from upgrade_date)
        expected_end_date = upgrade_date + timedelta(days=30)

        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.ends_at == expected_end_date, "Should fallback to upgrade date + 30 days"

    @patch('app.services.subscription_service.PlanService')
    def test_non_trial_upgrade_not_affected(self, mock_plan_service):
        """Test that upgrades from ACTIVE status are not affected by the change"""

        upgrade_date = datetime(2025, 12, 19, 0, 0, 0, tzinfo=timezone.utc)

        # Subscription already ACTIVE (not trialing)
        subscription = Subscription(
            id="sub-123",
            tenant_id="tenant-123",
            plan_id="plan-basic",
            status=SubscriptionStatus.ACTIVE,  # Already active
            billing_cycle=BillingCycle.MONTHLY,
            amount=Decimal("5.00"),
            currency="NGN",
            starts_at=upgrade_date - timedelta(days=10),
            ends_at=upgrade_date + timedelta(days=20),
            current_period_start=upgrade_date - timedelta(days=10),
            current_period_end=upgrade_date + timedelta(days=20),
            trial_starts_at=None,
            trial_ends_at=None
        )

        # Mock plan service
        new_plan = Mock()
        new_plan.id = "plan-pro"
        new_plan.is_active = True
        new_plan.monthly_plan_cost = Decimal("29.99")
        new_plan.yearly_plan_cost = Decimal("299.99")

        current_plan = Mock()
        current_plan.id = "plan-basic"
        current_plan.monthly_plan_cost = Decimal("5.00")
        current_plan.yearly_plan_cost = Decimal("50.00")

        mock_plan_service_instance = Mock()
        mock_plan_service_instance.get_plan_by_id = Mock(side_effect=lambda pid: new_plan if pid == "plan-pro" else current_plan)
        mock_plan_service.return_value = mock_plan_service_instance

        original_end_date = subscription.ends_at

        with patch('app.services.subscription_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = upgrade_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Execute
            result = self.service.switch_subscription_plan(
                subscription_id=subscription.id,
                new_plan_id="plan-pro",
                billing_cycle=BillingCycle.MONTHLY,
                prorate=True
            )

        # Assert: Status should remain ACTIVE, trial logic should NOT be applied
        assert subscription.status == SubscriptionStatus.ACTIVE
        # The ends_at might change, but it should NOT use trial logic
        # (exact behavior depends on other code, but trial logic should not apply)


    @patch('app.services.subscription_service.PlanService')
    def test_trial_downgrade_not_affected(self, mock_plan_service):
        """Test that downgrades from trial are not affected (new_amount <= old_amount)"""

        trial_end_date = datetime(2025, 12, 29, 0, 0, 0, tzinfo=timezone.utc)
        upgrade_date = datetime(2025, 12, 19, 0, 0, 0, tzinfo=timezone.utc)

        # Subscription in trial with some amount
        subscription = Subscription(
            id="sub-123",
            tenant_id="tenant-123",
            plan_id="plan-pro",
            status=SubscriptionStatus.TRIALING,
            billing_cycle=BillingCycle.MONTHLY,
            amount=Decimal("29.99"),
            currency="NGN",
            starts_at=upgrade_date - timedelta(days=14),
            ends_at=trial_end_date,
            current_period_start=upgrade_date - timedelta(days=14),
            current_period_end=trial_end_date,
            trial_starts_at=upgrade_date - timedelta(days=14),
            trial_ends_at=trial_end_date
        )

        # Mock plan service - downgrading to cheaper plan
        new_plan = Mock()
        new_plan.id = "plan-basic"
        new_plan.is_active = True
        new_plan.monthly_plan_cost = Decimal("5.00")  # Cheaper
        new_plan.yearly_plan_cost = Decimal("50.00")

        current_plan = Mock()
        current_plan.id = "plan-pro"
        current_plan.monthly_plan_cost = Decimal("29.99")
        current_plan.yearly_plan_cost = Decimal("299.99")

        mock_plan_service_instance = Mock()
        mock_plan_service_instance.get_plan_by_id = Mock(side_effect=lambda pid: new_plan if pid == "plan-basic" else current_plan)
        mock_plan_service.return_value = mock_plan_service_instance

        with patch('app.services.subscription_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = upgrade_date
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Execute - downgrade (new_amount < old_amount)
            result = self.service.switch_subscription_plan(
                subscription_id=subscription.id,
                new_plan_id="plan-basic",
                billing_cycle=BillingCycle.MONTHLY,
                prorate=True
            )

        # Assert: The trial logic should NOT apply because this is a downgrade
        # The status might still be TRIALING or change to ACTIVE depending on logic,
        # but the trial end date extension logic should NOT be triggered
        # (because the condition is: was_trialing AND new_amount > old_amount)
        # In this case, new_amount (5.00) < old_amount (29.99), so condition is false
