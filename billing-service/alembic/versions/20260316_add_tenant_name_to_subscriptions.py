"""Add tenant_name column to subscriptions table

Revision ID: 20260316_0001
Revises: 20260309_0001
Create Date: 2026-03-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260316_0001'
down_revision = '20260309_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('tenant_name', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'tenant_name')
