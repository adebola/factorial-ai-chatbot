"""create initial billing tables

Revision ID: 20251001_0000
Revises:
Create Date: 2025-10-01 00:00:00.000000

This is the base migration that creates all core billing tables.
Created retroactively to fix production deployment where tables don't exist.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20251001_0000'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all base billing tables"""

    # Check if tables already exist - if so, skip this migration
    # This handles the case where billing tables were created manually or by previous migration
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()

    if 'plans' in existing_tables:
        print("Billing tables already exist - skipping initial table creation")
        return

    # Create enums first (conditionally to avoid errors if they already exist)
    # Using raw SQL to handle duplicate_object exceptions
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE subscriptionstatus AS ENUM (
                'active', 'pending', 'past_due', 'cancelled', 'expired', 'trialing'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE billingcycle AS ENUM ('monthly', 'yearly');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE paymentstatus AS ENUM (
                'pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE paymentmethod AS ENUM (
                'card', 'bank_transfer', 'ussd', 'qr', 'mobile_money'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transactiontype AS ENUM (
                'subscription', 'upgrade', 'downgrade', 'renewal', 'refund'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Define enum types for use in columns (create_type=False prevents duplicate creation)
    subscriptionstatus_enum = postgresql.ENUM(
        'active', 'pending', 'past_due', 'cancelled', 'expired', 'trialing',
        name='subscriptionstatus', create_type=False
    )
    billingcycle_enum = postgresql.ENUM(
        'monthly', 'yearly',
        name='billingcycle', create_type=False
    )
    paymentstatus_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded',
        name='paymentstatus', create_type=False
    )
    paymentmethod_enum = postgresql.ENUM(
        'card', 'bank_transfer', 'ussd', 'qr', 'mobile_money',
        name='paymentmethod', create_type=False
    )
    transactiontype_enum = postgresql.ENUM(
        'subscription', 'upgrade', 'downgrade', 'renewal', 'refund',
        name='transactiontype', create_type=False
    )

    # 1. Create plans table (base columns only, additional columns added in next migration)
    op.create_table(
        'plans',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),

        # Usage Limits
        sa.Column('document_limit', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('website_limit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('daily_chat_limit', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('monthly_chat_limit', sa.Integer(), nullable=False, server_default='1500'),

        # Pricing
        sa.Column('monthly_plan_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('yearly_plan_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),

        # Features
        sa.Column('features', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Soft deletion
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_plans_id', 'plans', ['id'])
    op.create_index('ix_plans_name', 'plans', ['name'], unique=True)

    # 2. Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('plan_id', sa.String(36), nullable=False),

        # Subscription details
        sa.Column('status', subscriptionstatus_enum, nullable=False, server_default='pending'),
        sa.Column('billing_cycle', billingcycle_enum, nullable=False, server_default='monthly'),

        # Pricing
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),

        # Dates
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),

        # Trial
        sa.Column('trial_starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),

        # Cancellation
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),

        # Grace period
        sa.Column('grace_period_ends_at', sa.DateTime(timezone=True), nullable=True),

        # Auto-renewal
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default='true'),

        # Metadata
        sa.Column('subscription_metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_subscriptions_id', 'subscriptions', ['id'])
    op.create_index('ix_subscriptions_tenant_id', 'subscriptions', ['tenant_id'])
    op.create_index('ix_subscriptions_plan_id', 'subscriptions', ['plan_id'])
    op.create_index('ix_subscriptions_status', 'subscriptions', ['status'])
    op.create_foreign_key('fk_subscriptions_plan_id', 'subscriptions', 'plans', ['plan_id'], ['id'])

    # 3. Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),

        # Payment details
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),
        sa.Column('status', paymentstatus_enum, nullable=False, server_default='pending'),
        sa.Column('payment_method', paymentmethod_enum, nullable=True),
        sa.Column('transaction_type', transactiontype_enum, nullable=False, server_default='subscription'),

        # Paystack
        sa.Column('paystack_reference', sa.String(255), nullable=True, unique=True),
        sa.Column('paystack_access_code', sa.String(255), nullable=True),
        sa.Column('paystack_transaction_id', sa.String(255), nullable=True),

        # Processing
        sa.Column('gateway_response', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),

        # Description
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('payment_metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Refund
        sa.Column('refunded_amount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('refund_reason', sa.Text(), nullable=True),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),

        # Failure
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('failure_code', sa.String(50), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_payments_id', 'payments', ['id'])
    op.create_index('ix_payments_subscription_id', 'payments', ['subscription_id'])
    op.create_index('ix_payments_tenant_id', 'payments', ['tenant_id'])
    op.create_index('ix_payments_paystack_reference', 'payments', ['paystack_reference'], unique=True)
    op.create_index('ix_payments_paystack_transaction_id', 'payments', ['paystack_transaction_id'])
    op.create_index('ix_payments_status', 'payments', ['status'])
    op.create_foreign_key('fk_payments_subscription_id', 'payments', 'subscriptions', ['subscription_id'], ['id'])

    # 4. Create payment_methods table
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),

        # Method details
        sa.Column('type', paymentmethod_enum, nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),

        # Card info
        sa.Column('card_last_four', sa.String(4), nullable=True),
        sa.Column('card_brand', sa.String(20), nullable=True),
        sa.Column('card_exp_month', sa.Integer(), nullable=True),
        sa.Column('card_exp_year', sa.Integer(), nullable=True),

        # Bank info
        sa.Column('bank_name', sa.String(100), nullable=True),
        sa.Column('account_name', sa.String(255), nullable=True),

        # Paystack
        sa.Column('paystack_authorization_code', sa.String(255), nullable=True),
        sa.Column('paystack_customer_code', sa.String(255), nullable=True),

        # Metadata
        sa.Column('payment_method_metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_payment_methods_id', 'payment_methods', ['id'])
    op.create_index('ix_payment_methods_tenant_id', 'payment_methods', ['tenant_id'])
    op.create_index('ix_payment_methods_paystack_authorization_code', 'payment_methods', ['paystack_authorization_code'])
    op.create_index('ix_payment_methods_paystack_customer_code', 'payment_methods', ['paystack_customer_code'])

    # 5. Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),

        # Invoice details
        sa.Column('invoice_number', sa.String(50), nullable=False, unique=True),
        sa.Column('status', paymentstatus_enum, nullable=False, server_default='pending'),

        # Amounts
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),

        # Billing period
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),

        # Due date
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),

        # Invoice data
        sa.Column('line_items', postgresql.JSON(astext_type=sa.Text()), server_default='[]'),
        sa.Column('notes', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_invoices_id', 'invoices', ['id'])
    op.create_index('ix_invoices_subscription_id', 'invoices', ['subscription_id'])
    op.create_index('ix_invoices_tenant_id', 'invoices', ['tenant_id'])
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'], unique=True)
    op.create_foreign_key('fk_invoices_subscription_id', 'invoices', 'subscriptions', ['subscription_id'], ['id'])

    # 6. Create subscription_changes table
    op.create_table(
        'subscription_changes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),

        # Change details
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('previous_plan_id', sa.String(36), nullable=True),
        sa.Column('new_plan_id', sa.String(36), nullable=True),

        # Financial impact
        sa.Column('previous_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('new_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('prorated_amount', sa.Numeric(10, 2), nullable=True),

        # Change metadata
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('initiated_by', sa.String(50), nullable=True),
        sa.Column('change_metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Effective dates
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_subscription_changes_id', 'subscription_changes', ['id'])
    op.create_index('ix_subscription_changes_subscription_id', 'subscription_changes', ['subscription_id'])
    op.create_index('ix_subscription_changes_tenant_id', 'subscription_changes', ['tenant_id'])
    op.create_foreign_key('fk_subscription_changes_subscription_id', 'subscription_changes', 'subscriptions', ['subscription_id'], ['id'])

    # 7. Create paystack_webhooks table
    op.create_table(
        'paystack_webhooks',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),

        # Webhook details
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('paystack_event_id', sa.String(255), nullable=False, unique=True),

        # Processing status
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processing_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_processing_error', sa.Text(), nullable=True),

        # Event data
        sa.Column('raw_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('signature', sa.String(255), nullable=False),

        # Related records
        sa.Column('payment_id', sa.String(36), nullable=True),
        sa.Column('subscription_id', sa.String(36), nullable=True),

        # Timestamps
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_paystack_webhooks_id', 'paystack_webhooks', ['id'])
    op.create_index('ix_paystack_webhooks_event_type', 'paystack_webhooks', ['event_type'])
    op.create_index('ix_paystack_webhooks_paystack_event_id', 'paystack_webhooks', ['paystack_event_id'], unique=True)
    op.create_index('ix_paystack_webhooks_payment_id', 'paystack_webhooks', ['payment_id'])
    op.create_index('ix_paystack_webhooks_subscription_id', 'paystack_webhooks', ['subscription_id'])

    # 8. Create usage_tracking table
    op.create_table(
        'usage_tracking',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False),

        # Usage metrics
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),

        # Current usage
        sa.Column('documents_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('websites_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_chats_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('monthly_chats_used', sa.Integer(), nullable=False, server_default='0'),

        # API calls
        sa.Column('api_calls_made', sa.Integer(), nullable=False, server_default='0'),

        # Last reset dates
        sa.Column('daily_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('monthly_reset_at', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_usage_tracking_id', 'usage_tracking', ['id'])
    op.create_index('ix_usage_tracking_tenant_id', 'usage_tracking', ['tenant_id'])
    op.create_index('ix_usage_tracking_subscription_id', 'usage_tracking', ['subscription_id'])
    op.create_foreign_key('fk_usage_tracking_subscription_id', 'usage_tracking', 'subscriptions', ['subscription_id'], ['id'])

    # 9. Create refund_requests table
    op.create_table(
        'refund_requests',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('payment_id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),

        # Refund details
        sa.Column('requested_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('approved_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),

        # Status and processing
        sa.Column('status', paymentstatus_enum, nullable=False, server_default='pending'),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('admin_notes', sa.Text(), nullable=True),

        # Paystack
        sa.Column('paystack_refund_id', sa.String(255), nullable=True),
        sa.Column('gateway_response', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),

        # Approval workflow
        sa.Column('requested_by', sa.String(36), nullable=False),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_refund_requests_id', 'refund_requests', ['id'])
    op.create_index('ix_refund_requests_payment_id', 'refund_requests', ['payment_id'])
    op.create_index('ix_refund_requests_tenant_id', 'refund_requests', ['tenant_id'])
    op.create_index('ix_refund_requests_paystack_refund_id', 'refund_requests', ['paystack_refund_id'])
    op.create_foreign_key('fk_refund_requests_payment_id', 'refund_requests', 'payments', ['payment_id'], ['id'])


def downgrade() -> None:
    """Drop all tables in reverse order"""

    # Drop tables in reverse order (children first)
    op.drop_table('refund_requests')
    op.drop_table('usage_tracking')
    op.drop_table('paystack_webhooks')
    op.drop_table('subscription_changes')
    op.drop_table('invoices')
    op.drop_table('payment_methods')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('plans')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS transactiontype CASCADE')
    op.execute('DROP TYPE IF EXISTS paymentmethod CASCADE')
    op.execute('DROP TYPE IF EXISTS paymentstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS billingcycle CASCADE')
    op.execute('DROP TYPE IF EXISTS subscriptionstatus CASCADE')
