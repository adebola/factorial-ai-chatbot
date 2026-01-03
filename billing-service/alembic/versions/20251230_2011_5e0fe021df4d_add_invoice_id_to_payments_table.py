"""Add invoice_id to payments table

Revision ID: 5e0fe021df4d
Revises: 7eb23e862286
Create Date: 2025-12-30 20:11:01.424432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e0fe021df4d'
down_revision: Union[str, None] = '7eb23e862286'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add invoice_id column to payments table
    op.add_column('payments',
        sa.Column('invoice_id', sa.String(36), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_payments_invoice_id',
        'payments', 'invoices',
        ['invoice_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add index for performance
    op.create_index('ix_payments_invoice_id', 'payments', ['invoice_id'])

    # Backfill existing data: Update payments with their invoice_id
    # based on Invoice.related_payment_id
    op.execute("""
        UPDATE payments p
        SET invoice_id = i.id
        FROM invoices i
        WHERE i.related_payment_id = p.id
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_payments_invoice_id', 'payments')

    # Drop foreign key constraint
    op.drop_constraint('fk_payments_invoice_id', 'payments', type_='foreignkey')

    # Drop column
    op.drop_column('payments', 'invoice_id')
