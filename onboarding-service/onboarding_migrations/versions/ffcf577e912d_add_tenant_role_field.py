"""add_tenant_role_field

Revision ID: ffcf577e912d
Revises: bf2ab8c46db9
Create Date: 2025-08-17 12:23:08.795536

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffcf577e912d'
down_revision: Union[str, Sequence[str], None] = 'bf2ab8c46db9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    tenantrole_enum = sa.Enum('ADMIN', 'USER', name='tenantrole')
    tenantrole_enum.create(op.get_bind())
    
    # Add the role column as nullable first
    op.add_column('tenant', sa.Column('role', tenantrole_enum, nullable=True))
    
    # Set default values for existing tenants
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE tenant SET role = 'USER' WHERE role IS NULL"))
    
    # Make the column NOT NULL
    op.alter_column('tenant', 'role', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the role column
    op.drop_column('tenant', 'role')
    
    # Drop the enum type
    tenantrole_enum = sa.Enum('ADMIN', 'USER', name='tenantrole')
    tenantrole_enum.drop(op.get_bind())
