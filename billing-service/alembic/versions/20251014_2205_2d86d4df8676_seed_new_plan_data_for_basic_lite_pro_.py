"""Seed new plan data for Basic Lite Pro Enterprise

Revision ID: 2d86d4df8676
Revises: 336adf455524
Create Date: 2025-10-14 22:05:19.814339

"""
from typing import Sequence, Union
from datetime import datetime
import uuid
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column


# revision identifiers, used by Alembic.
revision: str = '2d86d4df8676'
down_revision: Union[str, None] = '336adf455524'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, delete any existing plans
    op.execute("DELETE FROM plans")

    # Define plans table for data insertion
    plans_table = table('plans',
        column('id', sa.String),
        column('name', sa.String),
        column('description', sa.Text),
        column('document_limit', sa.Integer),
        column('website_limit', sa.Integer),
        column('daily_chat_limit', sa.Integer),
        column('monthly_chat_limit', sa.Integer),
        column('max_document_size_mb', sa.Integer),
        column('max_pages_per_website', sa.Integer),
        column('monthly_plan_cost', sa.Numeric),
        column('yearly_plan_cost', sa.Numeric),
        column('has_trial', sa.Boolean),
        column('trial_days', sa.Integer),
        column('has_sentiment_analysis', sa.Boolean),
        column('has_conversational_workflow', sa.Boolean),
        column('has_api_access', sa.Boolean),
        column('has_custom_integrations', sa.Boolean),
        column('has_on_premise', sa.Boolean),
        column('analytics_level', sa.String),
        column('support_channels', sa.JSON),
        column('is_active', sa.Boolean),
        column('is_deleted', sa.Boolean),
        column('created_at', sa.DateTime)
    )

    # Insert new plans with reference data
    op.bulk_insert(plans_table, [
        {
            'id': str(uuid.uuid4()),
            'name': 'Basic',
            'description': 'Perfect for getting started with FactorialBot',
            'document_limit': 1,
            'website_limit': 1,
            'daily_chat_limit': 20,
            'monthly_chat_limit': 500,
            'max_document_size_mb': 2,
            'max_pages_per_website': 5,  # Max 5 pages
            'monthly_plan_cost': 50000.00,
            'yearly_plan_cost': 500000.00,
            'has_trial': True,
            'trial_days': 14,
            'has_sentiment_analysis': False,
            'has_conversational_workflow': False,
            'has_api_access': False,
            'has_custom_integrations': False,
            'has_on_premise': False,
            'analytics_level': 'basic',
            'support_channels': json.dumps(['email']),
            'is_active': True,
            'is_deleted': False,
            'created_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Lite',
            'description': 'For small businesses growing their customer support',
            'document_limit': 5,
            'website_limit': 1,
            'daily_chat_limit': 100,
            'monthly_chat_limit': 2500,
            'max_document_size_mb': 2,
            'max_pages_per_website': None,  # Unlimited pages within the site
            'monthly_plan_cost': 200000.00,
            'yearly_plan_cost': 2000000.00,
            'has_trial': False,
            'trial_days': 0,
            'has_sentiment_analysis': False,
            'has_conversational_workflow': False,
            'has_api_access': False,
            'has_custom_integrations': False,
            'has_on_premise': False,
            'analytics_level': 'basic',
            'support_channels': json.dumps(['email']),
            'is_active': True,
            'is_deleted': False,
            'created_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Pro',
            'description': 'For established businesses with high support volume',
            'document_limit': 20,
            'website_limit': 5,
            'daily_chat_limit': 400,
            'monthly_chat_limit': 10000,
            'max_document_size_mb': 2,
            'max_pages_per_website': None,  # Unlimited pages per site
            'monthly_plan_cost': 500000.00,
            'yearly_plan_cost': 5000000.00,
            'has_trial': False,
            'trial_days': 0,
            'has_sentiment_analysis': True,
            'has_conversational_workflow': True,
            'has_api_access': False,
            'has_custom_integrations': False,
            'has_on_premise': False,
            'analytics_level': 'basic',
            'support_channels': json.dumps(['email', 'phone']),
            'is_active': True,
            'is_deleted': False,
            'created_at': datetime.utcnow()
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Enterprise',
            'description': 'Custom solutions for large organizations',
            'document_limit': -1,  # Unlimited
            'website_limit': -1,  # Unlimited
            'daily_chat_limit': -1,  # Unlimited
            'monthly_chat_limit': -1,  # Unlimited
            'max_document_size_mb': 10,  # Larger files
            'max_pages_per_website': None,  # Unlimited pages
            'monthly_plan_cost': 0.00,  # Call for pricing
            'yearly_plan_cost': 0.00,  # Call for pricing
            'has_trial': False,
            'trial_days': 0,
            'has_sentiment_analysis': True,
            'has_conversational_workflow': True,
            'has_api_access': True,
            'has_custom_integrations': True,
            'has_on_premise': True,
            'analytics_level': 'full',
            'support_channels': json.dumps(['email', 'phone', 'dedicated']),
            'is_active': True,
            'is_deleted': False,
            'created_at': datetime.utcnow()
        }
    ])


def downgrade() -> None:
    # Delete the seeded plans
    op.execute("DELETE FROM plans WHERE name IN ('Basic', 'Lite', 'Pro', 'Enterprise')")
