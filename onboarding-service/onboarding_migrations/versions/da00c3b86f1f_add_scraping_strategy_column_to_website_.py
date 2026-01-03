"""Add scraping_strategy column to website_ingestions

Revision ID: da00c3b86f1f
Revises: 20251029_1400
Create Date: 2025-12-17 19:38:50.071617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da00c3b86f1f'
down_revision: Union[str, Sequence[str], None] = '20251029_1400'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add scraping_strategy column with default value 'auto'
    op.add_column(
        'website_ingestions',
        sa.Column('scraping_strategy', sa.String(50), nullable=False, server_default='auto')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove scraping_strategy column
    op.drop_column('website_ingestions', 'scraping_strategy')
