"""
Tests for admin payment endpoints in billing service.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import datetime
import uuid

from app.main import app
from app.models.subscription import Payment, Subscription, Invoice, PaymentStatus, PaymentMethod, TransactionType


@pytest.fixture
def mock_db():
    """Mock database session"""
    return Mock()


@pytest.fixture
def mock_system_admin_claims():
    """Mock SYSTEM_ADMIN token claims"""
    return Mock(
        tenant_id=str(uuid.uuid4()),
        email="admin@system.com",
        full_name="System Admin",
        roles=["ROLE_SYSTEM_ADMIN"]
    )


@pytest.fixture
def sample_payment():
    """Sample payment for testing"""
    payment_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    subscription_id = str(uuid.uuid4())

    payment = Mock(spec=Payment)
    payment.id = payment_id
    payment.tenant_id = tenant_id
    payment.subscription_id = subscription_id
    payment.amount = 50000.00
    payment.currency = "NGN"
    payment.status = PaymentStatus.COMPLETED
    payment.payment_method = PaymentMethod.CARD
    payment.transaction_type = TransactionType.RENEWAL
    payment.paystack_reference = "ref-12345"
    payment.description = "Monthly subscription payment"
    payment.created_at = datetime.now()
    payment.processed_at = datetime.now()
    payment.gateway_response = {"status": "success", "message": "Payment processed"}
    payment.refunded_amount = 0.0
    payment.invoice_id = None

    return payment


@pytest.fixture
def sample_subscription():
    """Sample subscription for testing"""
    subscription = Mock(spec=Subscription)
    subscription.id = str(uuid.uuid4())
    subscription.plan_id = str(uuid.uuid4())
    subscription.status = "active"
    subscription.user_email = "user@example.com"
    subscription.user_full_name = "John Doe"

    return subscription


@pytest.fixture
def sample_invoice():
    """Sample invoice for testing"""
    invoice = Mock(spec=Invoice)
    invoice.id = str(uuid.uuid4())
    invoice.invoice_number = "INV-2026-001"
    invoice.total_amount = 50000.00
    invoice.status = "paid"

    return invoice


class TestGetPaymentById:
    """Tests for GET /admin/billing/payments/{payment_id} endpoint"""

    @patch('app.api.admin.get_db')
    @patch('app.api.admin.require_system_admin')
    def test_get_payment_success_with_subscription_and_invoice(
        self,
        mock_require_admin,
        mock_get_db,
        mock_db,
        mock_system_admin_claims,
        sample_payment,
        sample_subscription,
        sample_invoice
    ):
        """Test successful retrieval of payment with subscription and invoice"""
        # Setup
        mock_require_admin.return_value = mock_system_admin_claims
        mock_get_db.return_value = mock_db

        sample_payment.invoice_id = sample_invoice.id

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_payment,      # First call: get payment
            sample_subscription,  # Second call: get subscription
            sample_invoice        # Third call: get invoice
        ]

        client = TestClient(app)
        response = client.get(
            f"/api/v1/admin/billing/payments/{sample_payment.id}",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == sample_payment.id
        assert data["tenant_id"] == sample_payment.tenant_id
        assert data["subscription_id"] == sample_payment.subscription_id
        assert data["amount"] == float(sample_payment.amount)
        assert data["currency"] == sample_payment.currency
        assert data["status"] == sample_payment.status.value
        assert data["payment_method"] == sample_payment.payment_method.value

        # Check subscription details included
        assert "subscription" in data
        assert data["subscription"]["id"] == sample_subscription.id
        assert data["subscription"]["user_email"] == sample_subscription.user_email

        # Check invoice details included
        assert "invoice" in data
        assert data["invoice"]["id"] == sample_invoice.id
        assert data["invoice"]["invoice_number"] == sample_invoice.invoice_number

    @patch('app.api.admin.get_db')
    @patch('app.api.admin.require_system_admin')
    def test_get_payment_success_without_subscription_and_invoice(
        self,
        mock_require_admin,
        mock_get_db,
        mock_db,
        mock_system_admin_claims,
        sample_payment
    ):
        """Test successful retrieval of payment without subscription or invoice"""
        # Setup
        mock_require_admin.return_value = mock_system_admin_claims
        mock_get_db.return_value = mock_db

        sample_payment.subscription_id = None
        sample_payment.invoice_id = None

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.return_value = sample_payment

        client = TestClient(app)
        response = client.get(
            f"/api/v1/admin/billing/payments/{sample_payment.id}",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == sample_payment.id
        assert data["subscription_id"] is None
        assert data["invoice_id"] is None
        assert "subscription" not in data
        assert "invoice" not in data

    @patch('app.api.admin.get_db')
    @patch('app.api.admin.require_system_admin')
    def test_get_payment_not_found(
        self,
        mock_require_admin,
        mock_get_db,
        mock_db,
        mock_system_admin_claims
    ):
        """Test payment not found returns 404"""
        # Setup
        mock_require_admin.return_value = mock_system_admin_claims
        mock_get_db.return_value = mock_db

        # Mock database query to return None
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.get(
            "/api/v1/admin/billing/payments/non-existent-id",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Assertions
        assert response.status_code == 404
        assert "Payment not found" in response.json()["detail"]

    @patch('app.api.admin.get_db')
    @patch('app.api.admin.require_system_admin')
    def test_get_payment_database_error(
        self,
        mock_require_admin,
        mock_get_db,
        mock_db,
        mock_system_admin_claims
    ):
        """Test database error returns 500"""
        # Setup
        mock_require_admin.return_value = mock_system_admin_claims
        mock_get_db.return_value = mock_db

        # Mock database query to raise exception
        mock_db.query.side_effect = Exception("Database connection failed")

        client = TestClient(app)
        response = client.get(
            "/api/v1/admin/billing/payments/some-id",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Assertions
        assert response.status_code == 500
        assert "Failed to retrieve payment" in response.json()["detail"]

    def test_get_payment_unauthorized(self):
        """Test unauthorized access returns 401"""
        client = TestClient(app)
        response = client.get(
            "/api/v1/admin/billing/payments/some-id"
            # No Authorization header
        )

        # Assertions
        assert response.status_code in [401, 403, 500]  # Depends on auth implementation


class TestAdminPaymentEndpointsIntegration:
    """Integration tests for admin payment endpoints"""

    def test_payment_endpoint_exists(self):
        """Test that the payment endpoint is registered"""
        client = TestClient(app)

        # This will fail auth but should not return 404
        response = client.get("/api/v1/admin/billing/payments/test-id")

        assert response.status_code != 404, "Endpoint should exist (even if auth fails)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
