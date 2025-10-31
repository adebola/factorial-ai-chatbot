"""Add pending plan fields to subscriptions

Revision ID: 3f8e9d2a1b5c
Revises: 2d86d4df8676
Create Date: 2025-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8e9d2a1b5c'
down_revision: Union[str, None] = '2d86d4df8676'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pending plan fields for scheduled downgrades"""

    # Add pending_plan_id column
    op.add_column('subscriptions',
        sa.Column('pending_plan_id', sa.String(36), nullable=True)
    )

    # Add pending_billing_cycle column
    op.add_column('subscriptions',
        sa.Column('pending_billing_cycle',
                  sa.Enum('monthly', 'yearly', name='billingcycle'),
                  nullable=True)
    )

    # Add pending_plan_effective_date column
    op.add_column('subscriptions',
        sa.Column('pending_plan_effective_date', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove pending plan fields"""

    # Drop columns in reverse order
    op.drop_column('subscriptions', 'pending_plan_effective_date')
    op.drop_column('subscriptions', 'pending_billing_cycle')
    op.drop_column('subscriptions', 'pending_plan_id')
