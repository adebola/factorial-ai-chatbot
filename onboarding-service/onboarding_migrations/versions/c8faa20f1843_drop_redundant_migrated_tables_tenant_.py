"""drop_redundant_migrated_tables_tenant_and_tenant_settings

Revision ID: c8faa20f1843
Revises: 8c7af17afd5f
Create Date: 2025-09-09 11:45:24.064499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8faa20f1843'
down_revision: Union[str, Sequence[str], None] = '8c7af17afd5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop redundant tables that have been migrated to OAuth2 Authorization Server.
    
    Tables being removed:
    - tenant_settings: Migrated to OAuth2 server's tenant_settings table
    - tenant: Migrated to OAuth2 server's tenants and users tables
    
    Order is important: Drop child tables first (tenant_settings), then parent (tenant)
    """
    
    # Step 1: Drop tenant_settings table (has FK to tenant table)
    op.drop_constraint('fk_tenant_settings_tenant_id', 'tenant_settings', type_='foreignkey')
    op.drop_index('ix_tenant_settings_tenant_id', table_name='tenant_settings')
    op.drop_index('ix_tenant_settings_id', table_name='tenant_settings')
    op.drop_table('tenant_settings')
    
    # Step 2: Drop tenant table (after all FK dependencies are removed)
    # First drop any remaining foreign key constraints that reference tenant
    # Note: plans.id is referenced by tenant.plan_id, but we're dropping tenant, so no issue
    op.drop_table('tenant')
    
    # Step 3: Drop the tenantrole enum type (no longer needed)
    op.execute("DROP TYPE IF EXISTS tenantrole")


def downgrade() -> None:
    """
    Rollback: Recreate the dropped tables for emergency rollback.
    
    WARNING: This rollback will create empty tables with the original structure,
    but will NOT restore any data that was in them when they were dropped.
    """
    
    # Step 1: Recreate tenantrole enum type
    op.execute("CREATE TYPE tenantrole AS ENUM ('ADMIN', 'USER')")
    
    # Step 2: Recreate tenant table first (parent table)
    op.create_table(
        'tenant',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False, unique=True),
        sa.Column('website_url', sa.String(500), nullable=True),
        sa.Column('api_key', sa.String(255), nullable=False, unique=True),
        sa.Column('username', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True, unique=True),
        sa.Column('role', sa.Enum('ADMIN', 'USER', name='tenantrole'), nullable=False, server_default='USER'),
        sa.Column('reset_token', sa.String(255), nullable=True),
        sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('plan_id', sa.String(36), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('config', sa.JSON, nullable=True, server_default='{}')
    )
    
    # Create indexes for tenant table
    op.create_index('ix_tenant_domain', 'tenant', ['domain'], unique=True)
    op.create_index('ix_tenant_api_key', 'tenant', ['api_key'], unique=True)
    op.create_index('ix_tenant_username', 'tenant', ['username'], unique=True)
    op.create_index('ix_tenant_email', 'tenant', ['email'], unique=True)
    op.create_index('ix_tenant_plan_id', 'tenant', ['plan_id'])
    
    # Create foreign key constraint to plans table
    op.create_foreign_key('fk_tenant_plan_id', 'tenant', 'plans', ['plan_id'], ['id'])
    
    # Step 3: Recreate tenant_settings table (child table)
    op.create_table(
        'tenant_settings',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('primary_color', sa.String(7), nullable=True),
        sa.Column('secondary_color', sa.String(7), nullable=True),
        sa.Column('company_logo_url', sa.String(1000), nullable=True),
        sa.Column('company_logo_object_name', sa.String(500), nullable=True),
        sa.Column('hover_text', sa.String(255), nullable=True),
        sa.Column('welcome_message', sa.Text, nullable=True),
        sa.Column('chat_window_title', sa.String(100), nullable=True),
        sa.Column('additional_settings', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create indexes for tenant_settings table
    op.create_index('ix_tenant_settings_id', 'tenant_settings', ['id'])
    op.create_index('ix_tenant_settings_tenant_id', 'tenant_settings', ['tenant_id'], unique=True)
    
    # Create foreign key constraint
    op.create_foreign_key('fk_tenant_settings_tenant_id', 'tenant_settings', 'tenant', ['tenant_id'], ['id'])
