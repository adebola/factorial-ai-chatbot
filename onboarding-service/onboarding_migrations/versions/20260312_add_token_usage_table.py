"""add_token_usage_table

Revision ID: 55b77abff552
Revises: ffcf577e912d
Create Date: 2026-03-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55b77abff552'
down_revision: Union[str, Sequence[str], None] = '20260224_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'token_usage',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=False),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('usage_type', sa.String(20), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_onb_token_usage_id', 'token_usage', ['id'])
    op.create_index('ix_onb_token_usage_tenant_id', 'token_usage', ['tenant_id'])
    op.create_index('ix_onb_token_usage_created_at', 'token_usage', ['created_at'])
    op.create_index('ix_onb_token_usage_tenant_created', 'token_usage', ['tenant_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_onb_token_usage_tenant_created', table_name='token_usage')
    op.drop_index('ix_onb_token_usage_created_at', table_name='token_usage')
    op.drop_index('ix_onb_token_usage_tenant_id', table_name='token_usage')
    op.drop_index('ix_onb_token_usage_id', table_name='token_usage')
    op.drop_table('token_usage')
