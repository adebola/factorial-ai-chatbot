"""add llm_providers and tenant_llm_selections tables

Revision ID: a1b2c3d4e5f6
Revises: 9e89bf09a7fc
Create Date: 2026-03-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9e89bf09a7fc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('requires_api_key', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('provider', 'model_id', name='uq_provider_model'),
    )

    op.create_table(
        'tenant_llm_selections',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('llm_provider_id', sa.String(36), sa.ForeignKey('llm_providers.id'), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('tenant_id', name='uq_tenant_llm_selection'),
    )


def downgrade() -> None:
    op.drop_table('tenant_llm_selections')
    op.drop_table('llm_providers')