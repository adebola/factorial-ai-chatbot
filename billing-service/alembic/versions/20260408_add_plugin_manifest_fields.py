"""Add plugin manifest fields to agentic_services and align observability row.

Adds the columns needed for the dynamic plugin/agentic-service catalog:
  - manifest          : entire most-recent manifest fetched from the plugin
  - ui_extensions     : denormalized list of admin-UI menu entries the plugin
                        contributes (separate from ui_hints, which is in-chat
                        widget presentation metadata)
  - health_status     : healthy | unhealthy | unknown
  - last_manifest_fetch_at
  - last_health_at

Also normalizes the existing observability row created in 20260320_obs_agent
so it matches the new naming convention used by the manifest:
  name        : observability_agent -> Observability
  service_key : obs-agent           -> observability

Revision ID: 20260408_plugin_manifest
Revises: 20260401_llm_configs
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260408_plugin_manifest'
down_revision = '20260401_llm_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agentic_services', sa.Column('manifest', sa.JSON(), nullable=True))
    op.add_column('agentic_services', sa.Column('ui_extensions', sa.JSON(), nullable=True))
    op.add_column(
        'agentic_services',
        sa.Column('health_status', sa.String(20), nullable=False, server_default='unknown'),
    )
    op.add_column('agentic_services', sa.Column('last_manifest_fetch_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agentic_services', sa.Column('last_health_at', sa.DateTime(timezone=True), nullable=True))

    # Normalize the existing observability row to the new conventions.
    # This is intentionally narrow — only touches the row we know about.
    op.execute(
        """
        UPDATE agentic_services
           SET name        = 'Observability',
               service_key = 'observability'
         WHERE id = 'de734f4b-92f3-43f4-97bc-6ed8217cc007'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE agentic_services
           SET name        = 'observability_agent',
               service_key = 'obs-agent'
         WHERE id = 'de734f4b-92f3-43f4-97bc-6ed8217cc007'
        """
    )
    op.drop_column('agentic_services', 'last_health_at')
    op.drop_column('agentic_services', 'last_manifest_fetch_at')
    op.drop_column('agentic_services', 'health_status')
    op.drop_column('agentic_services', 'ui_extensions')
    op.drop_column('agentic_services', 'manifest')
