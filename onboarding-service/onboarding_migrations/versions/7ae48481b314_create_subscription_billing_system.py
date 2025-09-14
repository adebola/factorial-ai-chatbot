"""create_subscription_billing_system

Revision ID: 7ae48481b314
Revises: 3dec14a5b6e0
Create Date: 2025-09-11 15:58:18.879982

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ae48481b314'
down_revision: Union[str, Sequence[str], None] = '3dec14a5b6e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create comprehensive subscription billing system."""
    
    # Note: Using string columns instead of enum types for now
    # Enum validation will be handled by the application layer
    
    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('plan_id', sa.String(36), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('billing_cycle', sa.String(20), nullable=False, server_default='monthly'),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trial_starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text, nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('grace_period_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_renew', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('subscription_metadata', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create foreign key constraint to plans table
    op.create_foreign_key('fk_subscriptions_plan_id', 'subscriptions', 'plans', ['plan_id'], ['id'])
    
    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('payment_method', sa.String(30), nullable=True),
        sa.Column('transaction_type', sa.String(30), nullable=False, server_default='subscription'),
        sa.Column('paystack_reference', sa.String(255), nullable=True, unique=True, index=True),
        sa.Column('paystack_access_code', sa.String(255), nullable=True),
        sa.Column('paystack_transaction_id', sa.String(255), nullable=True, index=True),
        sa.Column('gateway_response', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('payment_metadata', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('refunded_amount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('refund_reason', sa.Text, nullable=True),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text, nullable=True),
        sa.Column('failure_code', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create foreign key constraint to subscriptions table
    op.create_foreign_key('fk_payments_subscription_id', 'payments', 'subscriptions', ['subscription_id'], ['id'])
    
    # Create payment_methods table
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('card_last_four', sa.String(4), nullable=True),
        sa.Column('card_brand', sa.String(20), nullable=True),
        sa.Column('card_exp_month', sa.Integer, nullable=True),
        sa.Column('card_exp_year', sa.Integer, nullable=True),
        sa.Column('bank_name', sa.String(100), nullable=True),
        sa.Column('account_name', sa.String(255), nullable=True),
        sa.Column('paystack_authorization_code', sa.String(255), nullable=True, index=True),
        sa.Column('paystack_customer_code', sa.String(255), nullable=True, index=True),
        sa.Column('payment_method_metadata', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('invoice_number', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('line_items', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create foreign key constraint to subscriptions table
    op.create_foreign_key('fk_invoices_subscription_id', 'invoices', 'subscriptions', ['subscription_id'], ['id'])
    
    # Create subscription_changes table
    op.create_table(
        'subscription_changes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('subscription_id', sa.String(36), nullable=False, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('previous_plan_id', sa.String(36), nullable=True),
        sa.Column('new_plan_id', sa.String(36), nullable=True),
        sa.Column('previous_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('new_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('prorated_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('initiated_by', sa.String(50), nullable=True),
        sa.Column('change_metadata', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    
    # Create foreign key constraint to subscriptions table
    op.create_foreign_key('fk_subscription_changes_subscription_id', 'subscription_changes', 'subscriptions', ['subscription_id'], ['id'])
    
    # Create paystack_webhooks table
    op.create_table(
        'paystack_webhooks',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('paystack_event_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('processed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('processing_attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_processing_error', sa.Text, nullable=True),
        sa.Column('raw_data', sa.JSON, nullable=False),
        sa.Column('signature', sa.String(255), nullable=False),
        sa.Column('payment_id', sa.String(36), nullable=True, index=True),
        sa.Column('subscription_id', sa.String(36), nullable=True, index=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create usage_tracking table
    op.create_table(
        'usage_tracking',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('subscription_id', sa.String(36), nullable=False, index=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('documents_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('websites_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('daily_chats_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('monthly_chats_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('api_calls_made', sa.Integer, nullable=False, server_default='0'),
        sa.Column('daily_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('monthly_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create foreign key constraint to subscriptions table
    op.create_foreign_key('fk_usage_tracking_subscription_id', 'usage_tracking', 'subscriptions', ['subscription_id'], ['id'])
    
    # Create refund_requests table
    op.create_table(
        'refund_requests',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('payment_id', sa.String(36), nullable=False, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True, comment='Tenant data in OAuth2 server'),
        sa.Column('requested_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('approved_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='NGN'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('admin_notes', sa.Text, nullable=True),
        sa.Column('paystack_refund_id', sa.String(255), nullable=True, index=True),
        sa.Column('gateway_response', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('requested_by', sa.String(36), nullable=False),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now())
    )
    
    # Create foreign key constraint to payments table
    op.create_foreign_key('fk_refund_requests_payment_id', 'refund_requests', 'payments', ['payment_id'], ['id'])


def downgrade() -> None:
    """Drop subscription billing system."""
    
    # Drop tables in reverse order (child tables first)
    op.drop_table('refund_requests')
    op.drop_table('usage_tracking')
    op.drop_table('paystack_webhooks')
    op.drop_table('subscription_changes')
    op.drop_table('invoices')
    op.drop_table('payment_methods')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    
    # Note: No enum types to drop since we used string columns