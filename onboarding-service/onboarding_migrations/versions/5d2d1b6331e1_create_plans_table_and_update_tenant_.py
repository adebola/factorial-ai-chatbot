"""create_plans_table_and_update_tenant_

Revision ID: 5d2d1b6331e1
Revises: a64897682ecf
Create Date: 2025-08-21 16:41:00.000000

NOTE: This migration was originally created for the plans table,
but plans management has been moved to the billing-service.
This file is kept as a no-op stub to maintain the Alembic migration chain.
The actual plans table operations are now in billing-service/alembic/versions/

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2d1b6331e1'
down_revision: Union[str, Sequence[str], None] = 'a64897682ecf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    No-op migration stub.

    Originally created plans table, but plans management has been
    migrated to billing-service. This stub maintains the migration
    chain integrity.
    """
    pass


def downgrade() -> None:
    """No-op downgrade stub."""
    pass
