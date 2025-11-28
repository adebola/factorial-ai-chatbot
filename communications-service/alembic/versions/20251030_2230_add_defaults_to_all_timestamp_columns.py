"""Add defaults to all timestamp columns in communications tables

Revision ID: 20251030_2230
Revises: 20251030_2200
Create Date: 2025-10-30 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251030_2230'
down_revision = '20251030_2200'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add server defaults to all created_at and updated_at timestamp columns.

    This fixes NOT NULL violations that occurred because these columns were defined
    as nullable=False in migrations without DEFAULT clauses, while the SQLAlchemy
    models expect server_default=func.now().

    Affected tables:
    - email_messages.created_at
    - sms_messages.created_at
    - delivery_logs.created_at
    - message_templates.created_at
    - message_templates.updated_at
    """

    # Backfill any existing NULL values (if any exist)
    # This ensures no data loss if records somehow got created without timestamps

    op.execute("""
        UPDATE email_messages
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)

    op.execute("""
        UPDATE sms_messages
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)

    op.execute("""
        UPDATE delivery_logs
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)

    op.execute("""
        UPDATE message_templates
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)

    op.execute("""
        UPDATE message_templates
        SET updated_at = NOW()
        WHERE updated_at IS NULL
    """)

    # Add server defaults to all timestamp columns
    # PostgreSQL syntax for adding default to existing column

    op.execute("""
        ALTER TABLE email_messages
        ALTER COLUMN created_at
        SET DEFAULT NOW()
    """)

    op.execute("""
        ALTER TABLE sms_messages
        ALTER COLUMN created_at
        SET DEFAULT NOW()
    """)

    op.execute("""
        ALTER TABLE delivery_logs
        ALTER COLUMN created_at
        SET DEFAULT NOW()
    """)

    op.execute("""
        ALTER TABLE message_templates
        ALTER COLUMN created_at
        SET DEFAULT NOW()
    """)

    op.execute("""
        ALTER TABLE message_templates
        ALTER COLUMN updated_at
        SET DEFAULT NOW()
    """)


def downgrade() -> None:
    """Remove server defaults from all timestamp columns"""

    op.execute("""
        ALTER TABLE email_messages
        ALTER COLUMN created_at
        DROP DEFAULT
    """)

    op.execute("""
        ALTER TABLE sms_messages
        ALTER COLUMN created_at
        DROP DEFAULT
    """)

    op.execute("""
        ALTER TABLE delivery_logs
        ALTER COLUMN created_at
        DROP DEFAULT
    """)

    op.execute("""
        ALTER TABLE message_templates
        ALTER COLUMN created_at
        DROP DEFAULT
    """)

    op.execute("""
        ALTER TABLE message_templates
        ALTER COLUMN updated_at
        DROP DEFAULT
    """)
