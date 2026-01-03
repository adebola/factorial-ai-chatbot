"""create workflow_action_data table

Revision ID: 3b4c5d6e7f8a
Revises: 8b526191b098
Create Date: 2025-10-08 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3b4c5d6e7f8a'
down_revision = '8b526191b098'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow_action_data table
    op.create_table(
        'workflow_action_data',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False),
        sa.Column('action_name', sa.String(length=255), nullable=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance
    op.create_index('ix_workflow_action_data_id', 'workflow_action_data', ['id'])
    op.create_index('ix_workflow_action_data_tenant_id', 'workflow_action_data', ['tenant_id'])
    op.create_index('ix_workflow_action_data_workflow_id', 'workflow_action_data', ['workflow_id'])
    op.create_index('ix_workflow_action_data_execution_id', 'workflow_action_data', ['execution_id'])

    # Composite index for common queries
    op.create_index(
        'ix_workflow_action_data_tenant_workflow',
        'workflow_action_data',
        ['tenant_id', 'workflow_id']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_workflow_action_data_tenant_workflow', table_name='workflow_action_data')
    op.drop_index('ix_workflow_action_data_execution_id', table_name='workflow_action_data')
    op.drop_index('ix_workflow_action_data_workflow_id', table_name='workflow_action_data')
    op.drop_index('ix_workflow_action_data_tenant_id', table_name='workflow_action_data')
    op.drop_index('ix_workflow_action_data_id', table_name='workflow_action_data')

    # Drop table
    op.drop_table('workflow_action_data')
