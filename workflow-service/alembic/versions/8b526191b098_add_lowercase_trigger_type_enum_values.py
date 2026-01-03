"""Add lowercase trigger type enum values

Revision ID: 8b526191b098
Revises: 2a45ef8b095f
Create Date: 2025-09-30 14:43:59.087745

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b526191b098'
down_revision = '2a45ef8b095f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add lowercase values to the triggertype enum
    op.execute("ALTER TYPE triggertype ADD VALUE IF NOT EXISTS 'message'")
    op.execute("ALTER TYPE triggertype ADD VALUE IF NOT EXISTS 'intent'")
    op.execute("ALTER TYPE triggertype ADD VALUE IF NOT EXISTS 'keyword'")
    op.execute("ALTER TYPE triggertype ADD VALUE IF NOT EXISTS 'manual'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type and updating all references
    # For safety, we'll leave the lowercase values in place
    pass