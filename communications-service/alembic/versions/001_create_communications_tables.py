"""Create communications tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create message_status enum (check if exists first)
    message_status_enum = postgresql.ENUM(
        'pending', 'sent', 'delivered', 'failed', 'bounced', 'opened', 'clicked',
        name='messagestatus',
        create_type=False  # Don't auto-create when used in columns
    )
    message_status_enum.create(op.get_bind(), checkfirst=True)

    # Create provider_type enum (check if exists first)
    provider_type_enum = postgresql.ENUM(
        'sendgrid', 'twilio', 'mock',
        name='providertype',
        create_type=False  # Don't auto-create when used in columns
    )
    provider_type_enum.create(op.get_bind(), checkfirst=True)

    # Create template_type enum (check if exists first)
    template_type_enum = postgresql.ENUM(
        'email', 'sms',
        name='templatetype',
        create_type=False  # Don't auto-create when used in columns
    )
    template_type_enum.create(op.get_bind(), checkfirst=True)

    # Create email_messages table
    op.create_table('email_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('to_email', sa.String(length=255), nullable=False),
        sa.Column('to_name', sa.String(length=255), nullable=True),
        sa.Column('from_email', sa.String(length=255), nullable=False),
        sa.Column('from_name', sa.String(length=255), nullable=True),
        sa.Column('subject', sa.String(length=500), nullable=False),
        sa.Column('html_content', sa.Text(), nullable=True),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('status', message_status_enum, nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('attachments', sa.JSON(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('clicked_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('last_retry_at', sa.DateTime(), nullable=True),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('template_data', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_email_tenant_id', 'tenant_id'),
        sa.Index('idx_email_status', 'status'),
        sa.Index('idx_email_created_at', 'created_at'),
        sa.Index('idx_email_provider_message_id', 'provider_message_id')
    )

    # Create sms_messages table
    op.create_table('sms_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('to_phone', sa.String(length=20), nullable=False),
        sa.Column('from_phone', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', message_status_enum, nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('last_retry_at', sa.DateTime(), nullable=True),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('template_data', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_sms_tenant_id', 'tenant_id'),
        sa.Index('idx_sms_status', 'status'),
        sa.Index('idx_sms_created_at', 'created_at'),
        sa.Index('idx_sms_provider_message_id', 'provider_message_id')
    )

    # Create message_templates table
    op.create_table('message_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template_type', template_type_enum, nullable=False),
        sa.Column('subject_template', sa.String(length=500), nullable=True),
        sa.Column('html_template', sa.Text(), nullable=True),
        sa.Column('text_template', sa.Text(), nullable=True),
        sa.Column('variables', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('usage_count', sa.Integer(), default=0),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_template_tenant_id', 'tenant_id'),
        sa.Index('idx_template_type', 'template_type'),
        sa.Index('idx_template_active', 'is_active')
    )

    # Create message_type enum for delivery logs
    message_type_enum = postgresql.ENUM(
        'email', 'sms',
        name='messagetype',
        create_type=False  # Don't auto-create when used in columns
    )
    message_type_enum.create(op.get_bind(), checkfirst=True)

    # Create delivery_logs table
    op.create_table('delivery_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('message_id', sa.String(length=36), nullable=False),
        sa.Column('message_type', message_type_enum, nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('provider_name', sa.String(length=50), nullable=False),
        sa.Column('provider_response', sa.JSON(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_delivery_message_id', 'message_id'),
        sa.Index('idx_delivery_event_type', 'event_type'),
        sa.Index('idx_delivery_timestamp', 'occurred_at'),
        sa.Index('idx_delivery_tenant_id', 'tenant_id')
    )

    # Create tenant_settings table
    op.create_table('tenant_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('default_from_email', sa.String(length=255), nullable=True),
        sa.Column('default_from_name', sa.String(length=255), nullable=True),
        sa.Column('email_signature', sa.Text(), nullable=True),
        sa.Column('default_from_phone', sa.String(length=20), nullable=True),
        sa.Column('daily_email_limit', sa.Integer(), default=1000),
        sa.Column('daily_sms_limit', sa.Integer(), default=100),
        sa.Column('emails_sent_today', sa.Integer(), default=0),
        sa.Column('sms_sent_today', sa.Integer(), default=0),
        sa.Column('limit_reset_date', sa.DateTime(), nullable=False),
        sa.Column('enable_open_tracking', sa.Boolean(), default=True),
        sa.Column('enable_click_tracking', sa.Boolean(), default=True),
        sa.Column('enable_unsubscribe_link', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_tenant_settings_tenant_id', 'tenant_id'),
        sa.UniqueConstraint('tenant_id')
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table('tenant_settings')
    op.drop_table('delivery_logs')
    op.drop_table('message_templates')
    op.drop_table('sms_messages')
    op.drop_table('email_messages')

    # Drop enums (if they exist)
    op.execute('DROP TYPE IF EXISTS templatetype')
    op.execute('DROP TYPE IF EXISTS providertype')
    op.execute('DROP TYPE IF EXISTS messagestatus')
    op.execute('DROP TYPE IF EXISTS messagetype')