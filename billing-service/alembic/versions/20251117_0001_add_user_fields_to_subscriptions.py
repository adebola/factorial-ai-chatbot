"""Add user_email and user_full_name to subscriptions

Revision ID: 20251117_0001
Revises: 20251029_1330_insert_default_plans_reference_data
Create Date: 2025-11-17 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251117_0001'
down_revision = '20251029_1330'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add user_email and user_full_name columns to subscriptions table.

    These fields store user information from JWT token claims at subscription
    creation time, enabling scheduled jobs to send emails without requiring
    access tokens (which are not available in background jobs).
    """
    # Add user_email column (nullable initially for existing records)
    op.add_column('subscriptions', sa.Column('user_email', sa.String(255), nullable=True))

    # Add user_full_name column (nullable initially for existing records)
    op.add_column('subscriptions', sa.Column('user_full_name', sa.String(255), nullable=True))

    # Add indexes for efficient lookups
    op.create_index('ix_subscriptions_user_email', 'subscriptions', ['user_email'])

    # Note: We keep these nullable=True to allow existing subscriptions to remain valid.
    # New subscriptions created after this migration will populate these fields from JWT claims.


def downgrade():
    """Remove user_email and user_full_name columns from subscriptions table."""
    op.drop_index('ix_subscriptions_user_email', table_name='subscriptions')
    op.drop_column('subscriptions', 'user_full_name')
    op.drop_column('subscriptions', 'user_email')
