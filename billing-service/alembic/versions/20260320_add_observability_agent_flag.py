"""Add has_observability_agent flag to plans

Revision ID: 20260320_obs_agent
Revises: 20260316_add_tenant_name_to_subscriptions
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260320_obs_agent'
down_revision = '20260316_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('has_observability_agent', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('plans', 'has_observability_agent')
