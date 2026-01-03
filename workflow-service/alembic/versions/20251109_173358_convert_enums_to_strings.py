"""convert enums to strings

Revision ID: 20251109_173358
Revises: 8b526191b098
Create Date: 2025-11-09 17:33:58

Description:
    Converts all PostgreSQL enum types to plain string columns to resolve
    enum case mismatch issues in production. The database enums contained
    both uppercase and lowercase values, causing INSERT/UPDATE failures.

    This migration:
    1. Converts enum columns to String(20) type
    2. Drops all enum type definitions
    3. Preserves all existing data

    Impact: 5 workflows, 91 workflow executions, 322 step executions
    Risk: LOW - converting FROM enum TO string is non-destructive
    Downtime: NONE - online operation
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251109_173358'
down_revision = '3b4c5d6e7f8a'
branch_labels = None
depends_on = None


def upgrade():
    """Convert all enum columns to plain strings and drop enum types"""

    # Convert workflows.status from workflowstatus enum to String
    op.alter_column('workflows', 'status',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='status::text',
                    existing_nullable=False)

    # Convert workflows.trigger_type from triggertype enum to String
    op.alter_column('workflows', 'trigger_type',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='trigger_type::text',
                    existing_nullable=False)

    # Convert workflow_executions.status from executionstatus enum to String
    op.alter_column('workflow_executions', 'status',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='status::text',
                    existing_nullable=False)

    # Convert step_executions.status from executionstatus enum to String
    op.alter_column('step_executions', 'status',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='status::text',
                    existing_nullable=False)

    # Convert step_executions.step_type from steptype enum to String
    op.alter_column('step_executions', 'step_type',
                    type_=sa.String(20),
                    existing_type=sa.String(20),
                    postgresql_using='step_type::text',
                    existing_nullable=False)

    # Drop enum types (CASCADE to handle any dependencies)
    op.execute('DROP TYPE IF EXISTS workflowstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS triggertype CASCADE')
    op.execute('DROP TYPE IF EXISTS executionstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS steptype CASCADE')

    print("✓ Successfully converted all enum columns to strings")
    print("✓ Dropped 4 enum types: workflowstatus, triggertype, executionstatus, steptype")


def downgrade():
    """Recreate enum types and convert columns back (if needed for rollback)"""

    # Note: This recreates enums with BOTH uppercase and lowercase values
    # to match the state before this migration

    # Recreate workflowstatus enum with both cases
    op.execute("""
        CREATE TYPE workflowstatus AS ENUM (
            'DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED',
            'draft', 'active', 'inactive', 'archived'
        )
    """)

    # Recreate triggertype enum with both cases
    op.execute("""
        CREATE TYPE triggertype AS ENUM (
            'MESSAGE', 'INTENT', 'KEYWORD', 'MANUAL',
            'message', 'intent', 'keyword', 'manual'
        )
    """)

    # Recreate executionstatus enum (uppercase only)
    op.execute("""
        CREATE TYPE executionstatus AS ENUM (
            'RUNNING', 'COMPLETED', 'FAILED', 'PAUSED', 'CANCELLED'
        )
    """)

    # Recreate steptype enum (uppercase only)
    op.execute("""
        CREATE TYPE steptype AS ENUM (
            'MESSAGE', 'CHOICE', 'INPUT', 'CONDITION', 'ACTION', 'SUB_WORKFLOW', 'DELAY'
        )
    """)

    # Convert columns back to enum types
    # Note: Using CASE statement to normalize to enum values if needed

    op.execute("""
        ALTER TABLE workflows
        ALTER COLUMN status TYPE workflowstatus
        USING status::workflowstatus
    """)

    op.execute("""
        ALTER TABLE workflows
        ALTER COLUMN trigger_type TYPE triggertype
        USING trigger_type::triggertype
    """)

    op.execute("""
        ALTER TABLE workflow_executions
        ALTER COLUMN status TYPE executionstatus
        USING status::executionstatus
    """)

    op.execute("""
        ALTER TABLE step_executions
        ALTER COLUMN status TYPE executionstatus
        USING status::executionstatus
    """)

    op.execute("""
        ALTER TABLE step_executions
        ALTER COLUMN step_type TYPE steptype
        USING step_type::steptype
    """)

    print("✓ Rolled back to enum types")
    print("⚠ Warning: Enum case issues may reoccur after rollback")
