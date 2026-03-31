"""Add agentic service registry and tenant assignment tables

Revision ID: 20260322_svc_registry
Revises: 20260320_obs_agent
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260322_svc_registry'
down_revision = '20260320_obs_agent'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agentic_services',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('service_key', sa.String(50), unique=True, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('health_check_url', sa.String(500), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, server_default='agentic'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'tenant_service_assignments',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('service_id', sa.String(36), sa.ForeignKey('agentic_services.id'), nullable=False),
        sa.Column('assigned_by', sa.String(36), nullable=False),
        sa.Column('assigned_by_email', sa.String(255), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deactivated_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('tenant_id', 'service_id', name='uq_tenant_service'),
    )

    op.create_index('idx_tsa_tenant_id', 'tenant_service_assignments', ['tenant_id'])
    op.create_index('idx_tsa_service_id', 'tenant_service_assignments', ['service_id'])


def downgrade() -> None:
    op.drop_index('idx_tsa_service_id', table_name='tenant_service_assignments')
    op.drop_index('idx_tsa_tenant_id', table_name='tenant_service_assignments')
    op.drop_table('tenant_service_assignments')
    op.drop_table('agentic_services')
