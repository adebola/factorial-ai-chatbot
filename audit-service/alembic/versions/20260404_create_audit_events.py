"""Create audit_events table

Revision ID: 20260404_audit_events
Revises:
Create Date: 2026-04-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '20260404_audit_events'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), unique=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('actor_user_id', sa.String(36), nullable=True),
        sa.Column('actor_email', sa.String(255), nullable=True),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('action_type', sa.String(100), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.String(36), nullable=True),
        sa.Column('source_service', sa.String(50), nullable=False),
        sa.Column('trace_id', sa.String(32), nullable=True),
        sa.Column('span_id', sa.String(16), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('retention_days', sa.Integer(), nullable=True),
    )
    op.create_index('ix_audit_events_id', 'audit_events', ['id'])
    op.create_index('idx_audit_tenant_time', 'audit_events', ['tenant_id', 'created_at'])
    op.create_index('idx_audit_user_time', 'audit_events', ['actor_user_id', 'created_at'])
    op.create_index('idx_audit_action_time', 'audit_events', ['action_type', 'created_at'])
    op.create_index('idx_audit_trace', 'audit_events', ['trace_id'])
    op.create_index('idx_audit_resource', 'audit_events', ['resource_type', 'resource_id'])


def downgrade() -> None:
    op.drop_index('idx_audit_resource', table_name='audit_events')
    op.drop_index('idx_audit_trace', table_name='audit_events')
    op.drop_index('idx_audit_action_time', table_name='audit_events')
    op.drop_index('idx_audit_user_time', table_name='audit_events')
    op.drop_index('idx_audit_tenant_time', table_name='audit_events')
    op.drop_index('ix_audit_events_id', table_name='audit_events')
    op.drop_table('audit_events')
