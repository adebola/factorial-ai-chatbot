"""add workflow_intent_embeddings table for pgvector intent search

Revision ID: 20260223_intent_emb
Revises: 20251109_173358
Create Date: 2026-02-23

Description:
    Creates the workflow_intent_embeddings table with pgvector HNSW index
    for fast cosine similarity search on intent trigger patterns.
    Backfills existing intent embeddings from workflow trigger_config JSON.
"""
import json
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20260223_intent_emb'
down_revision = '20251109_173358'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create table using raw SQL because Alembic doesn't natively support vector types
    op.execute("""
        CREATE TABLE workflow_intent_embeddings (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL,
            workflow_id VARCHAR(36) REFERENCES workflows(id) ON DELETE SET NULL,
            pattern_text TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # B-tree index for tenant-scoped queries
    op.execute("CREATE INDEX idx_wie_tenant ON workflow_intent_embeddings(tenant_id)")
    op.execute("CREATE INDEX ix_workflow_intent_embeddings_id ON workflow_intent_embeddings(id)")

    # HNSW vector index for cosine similarity search
    op.execute("""
        CREATE INDEX idx_wie_embedding_hnsw ON workflow_intent_embeddings
        USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    """)

    # Backfill existing intent embeddings from trigger_config JSON
    conn = op.get_bind()
    workflows = conn.execute(text("""
        SELECT id, tenant_id, trigger_config
        FROM workflows
        WHERE trigger_type = 'intent'
          AND trigger_config IS NOT NULL
    """)).fetchall()

    for wf in workflows:
        config = wf.trigger_config
        if isinstance(config, str):
            config = json.loads(config)

        embeddings = (config or {}).get("intent_embeddings", [])
        for entry in embeddings:
            emb = entry.get("embedding")
            if emb:
                conn.execute(text("""
                    INSERT INTO workflow_intent_embeddings (id, tenant_id, workflow_id, pattern_text, embedding)
                    VALUES (:id, :tenant_id, :workflow_id, :pattern_text, cast(:embedding as vector))
                """), {
                    "id": str(uuid.uuid4()),
                    "tenant_id": wf.tenant_id,
                    "workflow_id": wf.id,
                    "pattern_text": entry.get("text", ""),
                    "embedding": str(emb)
                })


def downgrade() -> None:
    op.drop_table('workflow_intent_embeddings')
