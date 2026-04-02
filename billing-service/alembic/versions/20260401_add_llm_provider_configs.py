"""Add llm_provider_configs table for platform-wide model registry

Revision ID: 20260401_llm_configs
Revises: 20260401_enrich_svc
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260401_llm_configs'
down_revision = '20260401_enrich_svc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'llm_provider_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=True),
        sa.Column('max_context_tokens', sa.Integer(), nullable=False),
        sa.Column('context_limit_tokens', sa.Integer(), nullable=False),
        sa.Column('max_response_tokens', sa.Integer(), nullable=False, server_default=sa.text('4096')),
        sa.Column('cost_per_input_token', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('cost_per_output_token', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('provider', 'model_name', name='uq_provider_model'),
    )
    op.create_index('ix_llm_provider_configs_id', 'llm_provider_configs', ['id'])


def downgrade() -> None:
    op.drop_index('ix_llm_provider_configs_id', table_name='llm_provider_configs')
    op.drop_table('llm_provider_configs')
