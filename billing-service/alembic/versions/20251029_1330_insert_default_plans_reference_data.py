"""insert default plans reference data

Revision ID: 20251029_1330
Revises: 3f8e9d2a1b5c
Create Date: 2025-10-29 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251029_1330'
down_revision = '3f8e9d2a1b5c'
branch_labels = None
depends_on = None


def upgrade():
    """
    Insert 4 default plans as reference data.
    These plans must exist from day 1 for the billing system to function.
    Uses conditional INSERT to prevent duplicates on dev databases.
    """

    # Plan 1: Basic
    # Perfect for getting started with FactorialBot
    # 1 document, 1 website, 500 monthly chats
    # NGN 50,000/month with 30-day trial
    op.execute("""
        INSERT INTO plans (
            id,
            name,
            description,
            document_limit,
            website_limit,
            daily_chat_limit,
            monthly_chat_limit,
            monthly_plan_cost,
            yearly_plan_cost,
            is_active,
            is_deleted,
            max_document_size_mb,
            max_pages_per_website,
            has_trial,
            trial_days,
            has_sentiment_analysis,
            has_conversational_workflow,
            has_api_access,
            has_custom_integrations,
            has_on_premise,
            analytics_level,
            support_channels
        )
        SELECT
            'c2d04887-87f8-4d92-b0af-7d828cc9e69b',
            'Basic',
            'Perfect for getting started with FactorialBot',
            1,
            1,
            20,
            500,
            50000.00,
            500000.00,
            true,
            false,
            2,
            5,
            true,
            30,
            false,
            false,
            false,
            false,
            false,
            'basic',
            '["email"]'::json
        WHERE NOT EXISTS (
            SELECT 1 FROM plans WHERE name = 'Basic'
        );
    """)

    # Plan 2: Lite
    # For small businesses growing their customer support
    # 5 documents, 1 website, 2,500 monthly chats
    # NGN 200,000/month, no trial
    op.execute("""
        INSERT INTO plans (
            id,
            name,
            description,
            document_limit,
            website_limit,
            daily_chat_limit,
            monthly_chat_limit,
            monthly_plan_cost,
            yearly_plan_cost,
            is_active,
            is_deleted,
            max_document_size_mb,
            max_pages_per_website,
            has_trial,
            trial_days,
            has_sentiment_analysis,
            has_conversational_workflow,
            has_api_access,
            has_custom_integrations,
            has_on_premise,
            analytics_level,
            support_channels
        )
        SELECT
            '10d2cc6a-487b-4ef0-9176-4401d87881c4',
            'Lite',
            'For small businesses growing their customer support',
            5,
            1,
            100,
            2500,
            200000.00,
            2000000.00,
            true,
            false,
            2,
            NULL,
            false,
            0,
            false,
            false,
            false,
            false,
            false,
            'basic',
            '["email"]'::json
        WHERE NOT EXISTS (
            SELECT 1 FROM plans WHERE name = 'Lite'
        );
    """)

    # Plan 3: Pro
    # For established businesses with high support volume
    # 20 documents, 5 websites, 10,000 monthly chats
    # NGN 500,000/month with sentiment analysis & conversational workflow
    op.execute("""
        INSERT INTO plans (
            id,
            name,
            description,
            document_limit,
            website_limit,
            daily_chat_limit,
            monthly_chat_limit,
            monthly_plan_cost,
            yearly_plan_cost,
            is_active,
            is_deleted,
            max_document_size_mb,
            max_pages_per_website,
            has_trial,
            trial_days,
            has_sentiment_analysis,
            has_conversational_workflow,
            has_api_access,
            has_custom_integrations,
            has_on_premise,
            analytics_level,
            support_channels
        )
        SELECT
            'c3b59301-cc24-4f0f-aef1-717138a2cb4b',
            'Pro',
            'For established businesses with high support volume',
            20,
            5,
            400,
            10000,
            500000.00,
            5000000.00,
            true,
            false,
            2,
            NULL,
            false,
            0,
            true,
            true,
            false,
            false,
            false,
            'basic',
            '["email", "phone"]'::json
        WHERE NOT EXISTS (
            SELECT 1 FROM plans WHERE name = 'Pro'
        );
    """)

    # Plan 4: Enterprise
    # Custom solutions for large organizations
    # Unlimited everything, custom pricing
    # Full analytics, dedicated support, all premium features
    op.execute("""
        INSERT INTO plans (
            id,
            name,
            description,
            document_limit,
            website_limit,
            daily_chat_limit,
            monthly_chat_limit,
            monthly_plan_cost,
            yearly_plan_cost,
            is_active,
            is_deleted,
            max_document_size_mb,
            max_pages_per_website,
            has_trial,
            trial_days,
            has_sentiment_analysis,
            has_conversational_workflow,
            has_api_access,
            has_custom_integrations,
            has_on_premise,
            analytics_level,
            support_channels
        )
        SELECT
            'fa4784db-1231-432b-bd55-5a4176a642d7',
            'Enterprise',
            'Custom solutions for large organizations',
            -1,
            -1,
            -1,
            -1,
            0.00,
            0.00,
            true,
            false,
            10,
            NULL,
            false,
            0,
            true,
            true,
            true,
            true,
            true,
            'full',
            '["email", "phone", "dedicated"]'::json
        WHERE NOT EXISTS (
            SELECT 1 FROM plans WHERE name = 'Enterprise'
        );
    """)


def downgrade():
    """
    Remove the 4 default plans.
    WARNING: This will fail if any subscriptions reference these plans.
    """
    op.execute("""
        DELETE FROM plans
        WHERE name IN ('Basic', 'Lite', 'Pro', 'Enterprise');
    """)
