"""Create notification_logs table

Revision ID: 20251117_0002
Revises: 20251117_0001
Create Date: 2025-11-17 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '20251117_0002'
down_revision = '20251117_0001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create notification_logs table to track email notifications sent to users.

    This table prevents duplicate notifications and provides an audit trail
    of all billing-related emails sent to customers.
    """
    op.create_table(
        'notification_logs',

        # Primary key
        sa.Column('id', sa.String(36), primary_key=True, index=True),

        # Foreign keys
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('subscription_id', sa.String(36), nullable=True, index=True),

        # Notification details
        sa.Column('notification_type', sa.String(50), nullable=False, index=True),
        sa.Column('recipient_email', sa.String(255), nullable=False, index=True),
        sa.Column('recipient_name', sa.String(255), nullable=True),

        # Email content
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('template_used', sa.String(100), nullable=True),

        # Delivery status
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text, nullable=True),

        # Retry tracking
        sa.Column('retry_count', sa.Integer, nullable=False, default=0),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_retries', sa.Integer, nullable=False, default=3),

        # Related data
        sa.Column('related_payment_id', sa.String(36), nullable=True),
        sa.Column('related_invoice_id', sa.String(36), nullable=True),

        # Metadata
        sa.Column('notification_metadata', JSON, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )

    # Create indexes for efficient queries
    op.create_index(
        'ix_notification_logs_tenant_type',
        'notification_logs',
        ['tenant_id', 'notification_type']
    )

    op.create_index(
        'ix_notification_logs_subscription_type',
        'notification_logs',
        ['subscription_id', 'notification_type']
    )

    op.create_index(
        'ix_notification_logs_status_created',
        'notification_logs',
        ['status', 'created_at']
    )

    # Create index to prevent duplicate notifications within a time window
    op.create_index(
        'ix_notification_logs_duplicate_check',
        'notification_logs',
        ['tenant_id', 'notification_type', 'subscription_id', 'created_at']
    )


def downgrade():
    """Drop notification_logs table and its indexes."""
    op.drop_index('ix_notification_logs_duplicate_check', table_name='notification_logs')
    op.drop_index('ix_notification_logs_status_created', table_name='notification_logs')
    op.drop_index('ix_notification_logs_subscription_type', table_name='notification_logs')
    op.drop_index('ix_notification_logs_tenant_type', table_name='notification_logs')
    op.drop_table('notification_logs')
