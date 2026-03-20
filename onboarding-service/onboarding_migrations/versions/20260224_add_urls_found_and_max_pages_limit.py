"""Add urls_found and max_pages_limit columns to website_ingestions

Revision ID: 20260224_0001
Revises: da00c3b86f1f
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260224_0001'
down_revision: Union[str, Sequence[str], None] = 'da00c3b86f1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('website_ingestions', sa.Column('urls_found', sa.Integer(), server_default='0', nullable=True))
    op.add_column('website_ingestions', sa.Column('max_pages_limit', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('website_ingestions', 'max_pages_limit')
    op.drop_column('website_ingestions', 'urls_found')
