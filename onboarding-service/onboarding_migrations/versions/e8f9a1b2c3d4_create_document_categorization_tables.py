"""create_document_categorization_tables

Revision ID: e8f9a1b2c3d4
Revises: 4dd5c922d50d
Create Date: 2025-09-18 14:10:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8f9a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = '7ae48481b314'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create document categorization system tables."""

    # Create document_categories table
    op.create_table(
        'document_categories',
        sa.Column('id', sa.String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4())),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('parent_category_id', sa.String(36), nullable=True),
        sa.Column('color', sa.String(7), nullable=True),  # Hex color for UI
        sa.Column('icon', sa.String(50), nullable=True),  # Icon name
        sa.Column('is_system_category', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Add foreign key constraint for parent category
    op.create_foreign_key(
        'fk_document_categories_parent_category_id',
        'document_categories',
        'document_categories',
        ['parent_category_id'],
        ['id']
    )

    # Add unique constraint for tenant + name + parent combination
    op.create_unique_constraint(
        'uq_document_categories_tenant_name_parent',
        'document_categories',
        ['tenant_id', 'name', 'parent_category_id']
    )

    # Create document_tags table
    op.create_table(
        'document_tags',
        sa.Column('id', sa.String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4())),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('tag_type', sa.String(50), default='custom', nullable=False),  # 'auto', 'custom', 'system'
        sa.Column('usage_count', sa.Integer, default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Add unique constraint for tenant + name combination
    op.create_unique_constraint(
        'uq_document_tags_tenant_name',
        'document_tags',
        ['tenant_id', 'name']
    )

    # Create document_category_assignments table (many-to-many)
    op.create_table(
        'document_category_assignments',
        sa.Column('document_id', sa.String(36), nullable=False),
        sa.Column('category_id', sa.String(36), nullable=False),
        sa.Column('confidence_score', sa.Float, default=1.0, nullable=False),
        sa.Column('assigned_by', sa.String(20), default='user', nullable=False),  # 'user', 'ai', 'rule'
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('document_id', 'category_id')
    )

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_document_category_assignments_document_id',
        'document_category_assignments',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_document_category_assignments_category_id',
        'document_category_assignments',
        'document_categories',
        ['category_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Create document_tag_assignments table (many-to-many)
    op.create_table(
        'document_tag_assignments',
        sa.Column('document_id', sa.String(36), nullable=False),
        sa.Column('tag_id', sa.String(36), nullable=False),
        sa.Column('confidence_score', sa.Float, default=1.0, nullable=False),
        sa.Column('assigned_by', sa.String(20), default='user', nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('document_id', 'tag_id')
    )

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_document_tag_assignments_document_id',
        'document_tag_assignments',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_document_tag_assignments_tag_id',
        'document_tag_assignments',
        'document_tags',
        ['tag_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # NOTE: Vector database changes are handled separately in vector_db
    # The document_chunks table with categorization columns is in vector_db, not onboard_db
    # Run the manual script: docker-build/db-init/03-add-categorization-to-vector-db.sql

    # Create additional performance indexes
    op.create_index(
        'idx_document_categories_tenant_system',
        'document_categories',
        ['tenant_id', 'is_system_category']
    )

    op.create_index(
        'idx_document_tags_tenant_usage',
        'document_tags',
        ['tenant_id', 'usage_count']
    )

    # Insert default system categories
    op.execute("""
        INSERT INTO document_categories (id, tenant_id, name, description, color, icon, is_system_category, created_at)
        SELECT
            gen_random_uuid()::text,
            '',  -- Will be populated per tenant
            category_name,
            category_description,
            category_color,
            category_icon,
            true,
            NOW()
        FROM (VALUES
            ('Legal', 'Legal documents, contracts, compliance materials', '#1E40AF', 'legal'),
            ('Financial', 'Financial documents, invoices, reports, budgets', '#059669', 'financial'),
            ('HR', 'Human resources documents, policies, employee materials', '#DC2626', 'users'),
            ('Technical', 'Technical documentation, manuals, specifications', '#7C3AED', 'code'),
            ('Marketing', 'Marketing materials, campaigns, content', '#EA580C', 'megaphone')
        ) AS system_categories(category_name, category_description, category_color, category_icon)
        WHERE false;  -- Don't insert global categories, they will be tenant-specific
    """)


def downgrade() -> None:
    """Drop document categorization system tables."""

    # Drop indexes first
    op.drop_index('idx_document_tags_tenant_usage', 'document_tags')
    op.drop_index('idx_document_categories_tenant_system', 'document_categories')

    # NOTE: Vector database changes must be reverted manually in vector_db
    # The document_chunks columns should be dropped from vector_db, not onboard_db

    # Drop assignment tables (foreign keys will be dropped automatically)
    op.drop_table('document_tag_assignments')
    op.drop_table('document_category_assignments')

    # Drop main tables
    op.drop_table('document_tags')
    op.drop_table('document_categories')