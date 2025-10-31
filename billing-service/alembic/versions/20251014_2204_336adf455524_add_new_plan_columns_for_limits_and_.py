"""Add new plan columns for limits and features

Revision ID: 336adf455524
Revises: 20251001_0000
Create Date: 2025-10-14 22:04:03.770674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '336adf455524'
down_revision: Union[str, None] = '20251001_0000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to plans table
    op.add_column('plans', sa.Column('max_document_size_mb', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('plans', sa.Column('max_pages_per_website', sa.Integer(), nullable=True))
    op.add_column('plans', sa.Column('has_trial', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('trial_days', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('plans', sa.Column('has_sentiment_analysis', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('has_conversational_workflow', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('has_api_access', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('has_custom_integrations', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('has_on_premise', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('plans', sa.Column('analytics_level', sa.String(length=20), nullable=False, server_default='basic'))
    op.add_column('plans', sa.Column('support_channels', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove added columns
    op.drop_column('plans', 'support_channels')
    op.drop_column('plans', 'analytics_level')
    op.drop_column('plans', 'has_on_premise')
    op.drop_column('plans', 'has_custom_integrations')
    op.drop_column('plans', 'has_api_access')
    op.drop_column('plans', 'has_conversational_workflow')
    op.drop_column('plans', 'has_sentiment_analysis')
    op.drop_column('plans', 'trial_days')
    op.drop_column('plans', 'has_trial')
    op.drop_column('plans', 'max_pages_per_website')
    op.drop_column('plans', 'max_document_size_mb')
