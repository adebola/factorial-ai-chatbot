"""Add user_question and is_knowledge_gap columns to rag_quality_metrics

Revision ID: a3f8b2c1d4e5
Revises: 17d05ab982ab
Create Date: 2026-03-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3f8b2c1d4e5'
down_revision = '17d05ab982ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('rag_quality_metrics',
                  sa.Column('user_question', sa.String(500), nullable=True))
    op.add_column('rag_quality_metrics',
                  sa.Column('is_knowledge_gap', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('rag_quality_metrics', 'is_knowledge_gap')
    op.drop_column('rag_quality_metrics', 'user_question')
