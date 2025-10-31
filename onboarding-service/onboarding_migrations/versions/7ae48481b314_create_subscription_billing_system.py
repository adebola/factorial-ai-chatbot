"""create_subscription_billing_system

Revision ID: 7ae48481b314
Revises: 3dec14a5b6e0
Create Date: 2025-09-18 14:00:00.000000

NOTE: This migration was originally created for subscription billing tables,
but billing management has been moved to the billing-service.
This file is kept as a no-op stub to maintain the Alembic migration chain.
The actual billing table operations are now in billing-service/alembic/versions/

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ae48481b314'
down_revision: Union[str, Sequence[str], None] = '3dec14a5b6e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    No-op migration stub.

    Originally created subscription billing system tables, but billing
    management has been migrated to billing-service. This stub maintains
    the migration chain integrity.
    """
    pass


def downgrade() -> None:
    """No-op downgrade stub."""
    pass
