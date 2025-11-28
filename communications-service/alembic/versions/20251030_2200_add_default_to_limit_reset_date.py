"""Add default to limit_reset_date and created_at columns

Revision ID: 20251030_2200
Revises: 5f3e22e53553
Create Date: 2025-10-30 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251030_2200'
down_revision = '5f3e22e53553'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add server defaults to limit_reset_date and created_at columns in tenant_settings table.

    This fixes NOT NULL violations that occurred because these columns were defined
    as nullable=False without default values, while the SQLAlchemy model expects
    server_default=func.now().
    """
    # First, backfill any existing NULL values (if any exist)
    op.execute("""
        UPDATE tenant_settings
        SET limit_reset_date = NOW()
        WHERE limit_reset_date IS NULL
    """)

    op.execute("""
        UPDATE tenant_settings
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)

    # Add server defaults to columns
    # Note: PostgreSQL syntax for adding default to existing column
    op.execute("""
        ALTER TABLE tenant_settings
        ALTER COLUMN limit_reset_date
        SET DEFAULT NOW()
    """)

    op.execute("""
        ALTER TABLE tenant_settings
        ALTER COLUMN created_at
        SET DEFAULT NOW()
    """)


def downgrade() -> None:
    """Remove server defaults from limit_reset_date and created_at columns"""
    # Remove server defaults
    op.execute("""
        ALTER TABLE tenant_settings
        ALTER COLUMN limit_reset_date
        DROP DEFAULT
    """)

    op.execute("""
        ALTER TABLE tenant_settings
        ALTER COLUMN created_at
        DROP DEFAULT
    """)
