"""drop billing tables migrated to billing service

Revision ID: 20251029_1400
Revises: e8f9a1b2c3d4
Create Date: 2025-10-29 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251029_1400'
down_revision = 'e8f9a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    """
    Drop all billing-related tables from the onboarding service database.

    These tables were originally created in the onboarding service but have been
    migrated to the dedicated billing service (billing_db). This migration removes
    the redundant tables to ensure:

    1. No duplicate billing data across services
    2. Clean production deployment without billing artifacts in onboarding service
    3. Clear separation of concerns - onboarding handles tenant/document/website,
       billing service handles subscriptions/payments

    Tables being dropped:
    - subscriptions (parent table)
    - payments
    - payment_methods
    - invoices
    - subscription_changes
    - paystack_webhooks
    - usage_tracking
    - refund_requests

    Also drops related PostgreSQL enum types.
    """

    # Drop tables in correct order to avoid foreign key constraint violations
    # Child tables first, then parent tables

    # Step 1: Drop tables with foreign keys to subscriptions
    op.execute('DROP TABLE IF EXISTS usage_tracking CASCADE;')
    op.execute('DROP TABLE IF EXISTS subscription_changes CASCADE;')
    op.execute('DROP TABLE IF EXISTS paystack_webhooks CASCADE;')
    op.execute('DROP TABLE IF EXISTS refund_requests CASCADE;')
    op.execute('DROP TABLE IF EXISTS invoices CASCADE;')
    op.execute('DROP TABLE IF EXISTS payment_methods CASCADE;')
    op.execute('DROP TABLE IF EXISTS payments CASCADE;')

    # Step 2: Drop parent table (subscriptions)
    op.execute('DROP TABLE IF EXISTS subscriptions CASCADE;')

    # Step 3: Drop related PostgreSQL enum types
    # These enums were created for billing models and are no longer needed
    op.execute('DROP TYPE IF EXISTS subscriptionstatus CASCADE;')
    op.execute('DROP TYPE IF EXISTS paymentstatus CASCADE;')
    op.execute('DROP TYPE IF EXISTS paymentmethod CASCADE;')
    op.execute('DROP TYPE IF EXISTS billingcycle CASCADE;')
    op.execute('DROP TYPE IF EXISTS transactiontype CASCADE;')

    # Step 4: Drop any indexes related to billing tables (if they exist)
    # Note: CASCADE should handle this, but being explicit for clarity
    op.execute('DROP INDEX IF EXISTS ix_subscriptions_tenant_id;')
    op.execute('DROP INDEX IF EXISTS ix_subscriptions_status;')
    op.execute('DROP INDEX IF EXISTS ix_payments_subscription_id;')
    op.execute('DROP INDEX IF EXISTS ix_payments_status;')
    op.execute('DROP INDEX IF EXISTS ix_invoices_subscription_id;')
    op.execute('DROP INDEX IF EXISTS ix_usage_tracking_tenant_id;')


def downgrade():
    """
    Downgrade is not supported for this migration.

    The billing tables and data now live in the billing service database (billing_db).
    If you need billing functionality, use the billing service directly.

    Attempting to downgrade this migration would create empty tables without the
    proper data or relationships, leading to data inconsistency.
    """
    raise Exception(
        "Cannot downgrade: Billing tables have been permanently migrated to the "
        "billing service (billing_db). These tables should not be recreated in the "
        "onboarding service database. If you need billing functionality, use the "
        "billing service API endpoints instead."
    )
