"""Add PDF tracking fields to Invoice model

Revision ID: 7eb23e862286
Revises: 20251117_0002
Create Date: 2025-12-23 00:21:42.179975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7eb23e862286'
down_revision: Union[str, None] = '20251117_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add document_type column
    op.add_column(
        'invoices',
        sa.Column('document_type', sa.String(length=20), nullable=False, server_default='invoice')
    )

    # Add related_payment_id column with index
    op.add_column(
        'invoices',
        sa.Column('related_payment_id', sa.String(length=36), nullable=True)
    )
    op.create_index(
        'ix_invoices_related_payment_id',
        'invoices',
        ['related_payment_id'],
        unique=False
    )

    # Add pdf_generated_at column
    op.add_column(
        'invoices',
        sa.Column('pdf_generated_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add pdf_generation_error column
    op.add_column(
        'invoices',
        sa.Column('pdf_generation_error', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('invoices', 'pdf_generation_error')
    op.drop_column('invoices', 'pdf_generated_at')
    op.drop_index('ix_invoices_related_payment_id', table_name='invoices')
    op.drop_column('invoices', 'related_payment_id')
    op.drop_column('invoices', 'document_type')
