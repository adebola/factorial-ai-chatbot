"""Add custom_limits JSON column to subscriptions table

Revision ID: 20260309_0001
Revises: 20260224_0001
Create Date: 2026-03-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260309_0001'
down_revision = '20260224_0001'
branch_labels = None
depends_on = None


def upgrade():
    """Add custom_limits JSON column for per-subscription enterprise overrides."""
    op.add_column('subscriptions', sa.Column('custom_limits', sa.JSON(), nullable=True))


def downgrade():
    """Remove custom_limits column."""
    op.drop_column('subscriptions', 'custom_limits')
