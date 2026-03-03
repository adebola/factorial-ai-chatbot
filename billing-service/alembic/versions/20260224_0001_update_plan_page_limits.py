"""Update plan page limits for Basic Lite Pro

Revision ID: 20260224_0001
Revises: 20260103_2300
Create Date: 2026-02-24 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260224_0001'
down_revision = '20260103_2300'
branch_labels = None
depends_on = None


def upgrade():
    """
    Update plan limits:
    - Basic: max_pages_per_website 5 -> 10
    - Lite: max_pages_per_website NULL -> 50
    - Pro: website_limit 5 -> 1, max_pages_per_website NULL -> 200
    - Enterprise: unchanged (unlimited)
    """
    op.execute("UPDATE plans SET max_pages_per_website = 10 WHERE name = 'Basic'")
    op.execute("UPDATE plans SET max_pages_per_website = 50 WHERE name = 'Lite'")
    op.execute("UPDATE plans SET website_limit = 1, max_pages_per_website = 200 WHERE name = 'Pro'")


def downgrade():
    """Revert plan limits to original values"""
    op.execute("UPDATE plans SET max_pages_per_website = 5 WHERE name = 'Basic'")
    op.execute("UPDATE plans SET max_pages_per_website = NULL WHERE name = 'Lite'")
    op.execute("UPDATE plans SET website_limit = 5, max_pages_per_website = NULL WHERE name = 'Pro'")
