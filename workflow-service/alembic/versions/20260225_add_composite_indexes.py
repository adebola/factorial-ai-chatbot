"""Add composite indexes for hot query paths

Revision ID: 20260225_comp_idx
Revises: 20260224_requires_auth
Create Date: 2026-02-25

Description:
    Adds composite indexes to optimize the most frequent query patterns:
    - workflows(tenant_id, is_active, status) — trigger detection queries
    - workflow_executions(tenant_id, status) — execution lookups
    - workflow_states(session_id, expires_at) — state expiration checks
"""
from alembic import op

revision = '20260225_comp_idx'
down_revision = '20260224_requires_auth'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_workflows_tenant_active',
        'workflows',
        ['tenant_id', 'is_active', 'status'],
    )
    op.create_index(
        'idx_workflow_executions_tenant',
        'workflow_executions',
        ['tenant_id', 'status'],
    )
    op.create_index(
        'idx_workflow_states_session',
        'workflow_states',
        ['session_id', 'expires_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_workflow_states_session', table_name='workflow_states')
    op.drop_index('idx_workflow_executions_tenant', table_name='workflow_executions')
    op.drop_index('idx_workflows_tenant_active', table_name='workflows')
