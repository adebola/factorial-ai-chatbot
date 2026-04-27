"""Create legal service tables — workspaces, documents, workspace_documents.

Revision ID: 001_legal_tables
Revises: None
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = '001_legal_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Workspaces
    op.create_table(
        'workspaces',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('workspace_type', sa.String(50), nullable=False, server_default='project'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_by_email', sa.String(255), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False),
        sa.Column('minio_path', sa.String(1000), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('processing_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('uploaded_by', sa.String(36), nullable=True),
        sa.Column('uploaded_by_email', sa.String(255), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Workspace ↔ Document join (many-to-many, soft membership via removed_at)
    op.create_table(
        'workspace_documents',
        sa.Column('id', sa.String(36), primary_key=True, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('added_by', sa.String(36), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('removed_by', sa.String(36), nullable=True),
    )
    op.create_index('idx_wd_workspace_id', 'workspace_documents', ['workspace_id'])
    op.create_index('idx_wd_document_id', 'workspace_documents', ['document_id'])


def downgrade() -> None:
    op.drop_index('idx_wd_document_id', table_name='workspace_documents')
    op.drop_index('idx_wd_workspace_id', table_name='workspace_documents')
    op.drop_table('workspace_documents')
    op.drop_table('documents')
    op.drop_table('workspaces')
