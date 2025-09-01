"""Create Tenant Table

Revision ID: fb67285677a0
Revises: 
Create Date: 2025-08-13 13:27:08.727241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pydantic import UUID4

# revision identifiers, used by Alembic.
revision: str = 'fb67285677a0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tenant',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False, default=lambda: str(UUID4())),
        sa.Column('domain', sa.String(255), nullable=False, unique=True),
        sa.Column('website_url', sa.String(255), nullable=True),
        sa.Column('api_key', sa.String(64), nullable=False, unique=True),
        sa.Column('subscription_tier', sa.String(50), default='basic', nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('config', sa.JSON, nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tenant')
