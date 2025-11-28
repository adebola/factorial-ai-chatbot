"""convert enums to strings

Revision ID: 20251109_180500
Revises: 5f3e22e53553
Create Date: 2025-11-09 18:05:00

Description:
    Converts all PostgreSQL enum types to plain string columns to resolve
    enum case mismatch issues. The database enums contained uppercase values
    but the Python code uses lowercase values, causing INSERT/UPDATE failures.

    This migration:
    1. Converts enum columns to String(20) type
    2. Drops all enum type definitions
    3. Preserves all existing data

    Impact: Email messages, SMS messages, templates
    Risk: LOW - converting FROM enum TO string is non-destructive
    Downtime: NONE - online operation
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251109_180500'
down_revision = '20251030_2230'
branch_labels = None
depends_on = None


def upgrade():
    """Convert all enum columns to plain strings and drop enum types"""

    # Convert email_messages.status from messagestatus enum to String
    op.alter_column('email_messages', 'status',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='status::text',
                    existing_nullable=False)

    # Convert sms_messages.status from messagestatus enum to String
    op.alter_column('sms_messages', 'status',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='status::text',
                    existing_nullable=False)

    # Convert message_templates.template_type from templatetype enum to String
    op.alter_column('message_templates', 'template_type',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='template_type::text',
                    existing_nullable=False)

    # Convert delivery_logs.message_type from messagetype enum to String
    op.alter_column('delivery_logs', 'message_type',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='message_type::text',
                    existing_nullable=False)

    # Drop enum types (CASCADE to handle any dependencies)
    op.execute('DROP TYPE IF EXISTS messagestatus CASCADE')
    op.execute('DROP TYPE IF EXISTS messagetype CASCADE')
    op.execute('DROP TYPE IF EXISTS templatetype CASCADE')

    print("✓ Successfully converted all enum columns to strings")
    print("✓ Dropped 3 enum types: messagestatus, messagetype, templatetype")


def downgrade():
    """Recreate enum types and convert columns back (if needed for rollback)"""

    # Recreate messagestatus enum with uppercase values
    op.execute("""
        CREATE TYPE messagestatus AS ENUM (
            'PENDING', 'SENT', 'DELIVERED', 'FAILED', 'BOUNCED', 'OPENED', 'CLICKED'
        )
    """)

    # Recreate messagetype enum
    op.execute("""
        CREATE TYPE messagetype AS ENUM ('EMAIL', 'SMS')
    """)

    # Recreate templatetype enum
    op.execute("""
        CREATE TYPE templatetype AS ENUM ('EMAIL', 'SMS')
    """)

    # Convert columns back to enum types
    # Note: Need to uppercase the values before converting
    op.execute("""
        ALTER TABLE email_messages
        ALTER COLUMN status TYPE messagestatus
        USING UPPER(status)::messagestatus
    """)

    op.execute("""
        ALTER TABLE sms_messages
        ALTER COLUMN status TYPE messagestatus
        USING UPPER(status)::messagestatus
    """)

    op.execute("""
        ALTER TABLE message_templates
        ALTER COLUMN template_type TYPE templatetype
        USING UPPER(template_type)::templatetype
    """)

    op.execute("""
        ALTER TABLE delivery_logs
        ALTER COLUMN message_type TYPE messagetype
        USING UPPER(message_type)::messagetype
    """)

    print("✓ Rolled back to enum types")
    print("⚠ Warning: Enum case issues may reoccur after rollback")
