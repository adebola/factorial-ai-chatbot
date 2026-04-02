"""Add icon_url, capabilities, ui_hints to agentic_services

Revision ID: 20260401_enrich_svc
Revises: 20260322_svc_registry
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260401_enrich_svc'
down_revision = '20260322_svc_registry'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agentic_services', sa.Column('icon_url', sa.String(500), nullable=True))
    op.add_column('agentic_services', sa.Column('capabilities', sa.JSON(), nullable=True))
    op.add_column('agentic_services', sa.Column('ui_hints', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('agentic_services', 'ui_hints')
    op.drop_column('agentic_services', 'capabilities')
    op.drop_column('agentic_services', 'icon_url')
