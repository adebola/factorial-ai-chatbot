"""drop_tenantrole_enum_type

Revision ID: 3dec14a5b6e0
Revises: c8faa20f1843
Create Date: 2025-09-09 11:54:10.176489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3dec14a5b6e0'
down_revision: Union[str, Sequence[str], None] = 'c8faa20f1843'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the remaining tenantrole enum type that was left behind."""
    op.execute("DROP TYPE IF EXISTS tenantrole")


def downgrade() -> None:
    """Recreate the tenantrole enum type."""
    op.execute("CREATE TYPE tenantrole AS ENUM ('ADMIN', 'USER')")
