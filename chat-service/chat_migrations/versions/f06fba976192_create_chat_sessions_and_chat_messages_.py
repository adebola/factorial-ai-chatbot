"""create_chat_sessions_and_chat_messages_tables

Revision ID: f06fba976192
Revises: 
Create Date: 2025-08-20 13:08:32.061336

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f06fba976192'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable UUID extension for PostgreSQL
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create a chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(36), nullable=False, server_default=sa.text('uuid_generate_v4()::text')),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('user_identifier', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_tenant_id'), 'chat_sessions', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_session_id'), 'chat_sessions', ['session_id'], unique=True)
    
    # Create a chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(36), nullable=False, server_default=sa.text('uuid_generate_v4()::text')),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('message_type', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(op.f('ix_chat_messages_tenant_id'), 'chat_messages', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop chat_messages table
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_tenant_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    
    # Drop chat_sessions table
    op.drop_index(op.f('ix_chat_sessions_session_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_tenant_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
    
    # Note: We don't drop the uuid-ossp extension as other tables might be using it
