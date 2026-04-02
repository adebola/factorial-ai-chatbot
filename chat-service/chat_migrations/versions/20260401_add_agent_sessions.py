"""Add agent_sessions and agent_messages tables

Revision ID: 20260401_agent_sessions
Revises: 44a669aee441
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260401_agent_sessions'
down_revision: Union[str, None] = '44a669aee441'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('user_email', sa.String(255), nullable=True),
        sa.Column('user_full_name', sa.String(255), nullable=True),
        sa.Column('service_key', sa.String(50), nullable=False),
        sa.Column('parent_session_id', sa.String(36), nullable=True),
        sa.Column('context_summary', sa.Text(), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('total_tokens_used', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('context_limit_tokens', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_activity', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_agent_sessions_id', 'agent_sessions', ['id'])
    op.create_index('ix_agent_sessions_tenant_id', 'agent_sessions', ['tenant_id'])
    op.create_index('ix_agent_sessions_user_id', 'agent_sessions', ['user_id'])
    op.create_index('ix_agent_sessions_service_key', 'agent_sessions', ['service_key'])
    op.create_index(
        'idx_agent_sessions_tenant_service_status',
        'agent_sessions',
        ['tenant_id', 'service_key', 'status'],
    )

    op.create_table(
        'agent_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('agent_sessions.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('structured_blocks', sa.JSON(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('message_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_agent_messages_id', 'agent_messages', ['id'])
    op.create_index('ix_agent_messages_session_id', 'agent_messages', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_agent_messages_session_id', table_name='agent_messages')
    op.drop_index('ix_agent_messages_id', table_name='agent_messages')
    op.drop_table('agent_messages')
    op.drop_index('idx_agent_sessions_tenant_service_status', table_name='agent_sessions')
    op.drop_index('ix_agent_sessions_service_key', table_name='agent_sessions')
    op.drop_index('ix_agent_sessions_user_id', table_name='agent_sessions')
    op.drop_index('ix_agent_sessions_tenant_id', table_name='agent_sessions')
    op.drop_index('ix_agent_sessions_id', table_name='agent_sessions')
    op.drop_table('agent_sessions')
