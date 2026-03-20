"""add requires_auth column to workflows

Revision ID: 20260224_requires_auth
Revises: 20260223_intent_emb
Create Date: 2026-02-24

Description:
    Adds a requires_auth boolean column to the workflows table.
    When true, the workflow can only be executed by authenticated users.
    All existing workflows default to false (backward-compatible).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260224_requires_auth'
down_revision = '20260223_intent_emb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workflows',
        sa.Column('requires_auth', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )


def downgrade() -> None:
    op.drop_column('workflows', 'requires_auth')
