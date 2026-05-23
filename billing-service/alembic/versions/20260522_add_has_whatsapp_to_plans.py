"""Add has_whatsapp flag to plans

Revision ID: 20260522_whatsapp
Revises: 20260408_plugin_manifest
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260522_whatsapp'
down_revision = '20260408_plugin_manifest'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('has_whatsapp', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('plans', 'has_whatsapp')
