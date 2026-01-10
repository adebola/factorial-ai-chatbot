"""Create admin_actions audit table

Revision ID: 20260103_2300
Revises: 5e0fe021df4d
Create Date: 2026-01-03 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, JSONB


# revision identifiers, used by Alembic.
revision = '20260103_2300'
down_revision = '5e0fe021df4d'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create admin_actions table to track all administrative operations.

    This table provides a comprehensive audit trail of all admin actions
    for compliance, debugging, and security purposes.
    """
    op.create_table(
        'admin_actions',

        # Primary key
        sa.Column('id', sa.String(36), primary_key=True, index=True),

        # Admin user information
        sa.Column('admin_user_id', sa.String(36), nullable=False, index=True),
        sa.Column('admin_email', sa.String(255), nullable=False),
        sa.Column('admin_full_name', sa.String(255), nullable=True),

        # Action details
        sa.Column('action_type', sa.String(50), nullable=False, index=True),
        sa.Column('target_type', sa.String(50), nullable=False, index=True),
        sa.Column('target_id', sa.String(36), nullable=False, index=True),
        sa.Column('target_tenant_id', sa.String(36), nullable=True, index=True),

        # State tracking
        sa.Column('before_state', JSONB, nullable=True),
        sa.Column('after_state', JSONB, nullable=True),

        # Reason and context
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),

        # Additional metadata
        sa.Column('action_metadata', JSONB, nullable=True, server_default='{}'),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for efficient queries
    op.create_index(
        'ix_admin_actions_admin_user',
        'admin_actions',
        ['admin_user_id']
    )

    op.create_index(
        'ix_admin_actions_action_type',
        'admin_actions',
        ['action_type']
    )

    op.create_index(
        'ix_admin_actions_target',
        'admin_actions',
        ['target_type', 'target_id']
    )

    op.create_index(
        'ix_admin_actions_tenant',
        'admin_actions',
        ['target_tenant_id']
    )

    op.create_index(
        'ix_admin_actions_created',
        'admin_actions',
        ['created_at']
    )

    # Composite index for common query patterns
    op.create_index(
        'ix_admin_actions_tenant_action_type',
        'admin_actions',
        ['target_tenant_id', 'action_type', 'created_at']
    )


def downgrade():
    """Drop admin_actions table and its indexes."""
    op.drop_index('ix_admin_actions_tenant_action_type', table_name='admin_actions')
    op.drop_index('ix_admin_actions_created', table_name='admin_actions')
    op.drop_index('ix_admin_actions_tenant', table_name='admin_actions')
    op.drop_index('ix_admin_actions_target', table_name='admin_actions')
    op.drop_index('ix_admin_actions_action_type', table_name='admin_actions')
    op.drop_index('ix_admin_actions_admin_user', table_name='admin_actions')
    op.drop_table('admin_actions')
