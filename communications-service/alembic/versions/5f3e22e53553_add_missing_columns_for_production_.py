"""Add missing columns for production compatibility

Revision ID: 5f3e22e53553
Revises: 001
Create Date: 2025-09-27 02:06:50.328078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f3e22e53553'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns to email_messages table
    connection = op.get_bind()

    # Check if retry_count exists before adding it
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='retry_count'
    """))
    if not result.fetchone():
        op.add_column('email_messages', sa.Column('retry_count', sa.Integer(), nullable=True, default=0))

    # Check if last_retry_at exists before adding it
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='last_retry_at'
    """))
    if not result.fetchone():
        op.add_column('email_messages', sa.Column('last_retry_at', sa.DateTime(), nullable=True))

    # Check if updated_at exists before adding it
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('email_messages', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # Add missing columns to sms_messages table
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='retry_count'
    """))
    if not result.fetchone():
        op.add_column('sms_messages', sa.Column('retry_count', sa.Integer(), nullable=True, default=0))

    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='last_retry_at'
    """))
    if not result.fetchone():
        op.add_column('sms_messages', sa.Column('last_retry_at', sa.DateTime(), nullable=True))

    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('sms_messages', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove added columns from email_messages if they exist
    connection = op.get_bind()

    # Check and drop retry_count from email_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='retry_count'
    """))
    if result.fetchone():
        op.drop_column('email_messages', 'retry_count')

    # Check and drop last_retry_at from email_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='last_retry_at'
    """))
    if result.fetchone():
        op.drop_column('email_messages', 'last_retry_at')

    # Check and drop updated_at from email_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='email_messages' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('email_messages', 'updated_at')

    # Check and drop retry_count from sms_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='retry_count'
    """))
    if result.fetchone():
        op.drop_column('sms_messages', 'retry_count')

    # Check and drop last_retry_at from sms_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='last_retry_at'
    """))
    if result.fetchone():
        op.drop_column('sms_messages', 'last_retry_at')

    # Check and drop updated_at from sms_messages
    result = connection.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='sms_messages' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('sms_messages', 'updated_at')