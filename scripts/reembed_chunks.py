#!/usr/bin/env python3
"""
Re-embed stored OpenAI embeddings with a different model.

Supports two tables:
  * vectors.document_chunks            (vector_db)    — RAG chunks
  * public.workflow_intent_embeddings  (workflow_db)  — workflow trigger patterns

When/why to run:
  After the codebase switches OPENAI_EMBEDDING_MODEL from one model to
  another (e.g. text-embedding-ada-002 → text-embedding-3-small), the
  embeddings stored in the DB are still from the OLD model. Query
  embeddings (made by the new model) won't align with them, so retrieval
  / trigger matching quality temporarily degrades. This script re-embeds
  every row with the target model so similarity realigns.

What it does (per target):
  CHUNKS:
    1. Scan vectors.document_chunks (optionally filtered by tenant).
    2. For each chunk reconstruct embed text as
          f"{section_title}\\n\\n{content}"   (if section_title set)
          else                                  content
       — mirrors PgVectorIngestionService so the HTML-aware section boost
       is preserved.
    3. Call OpenAI embeddings.create() in batches; UPDATE embedding.

  INTENTS:
    1. Scan workflow_intent_embeddings (optionally filtered by tenant).
    2. Embed pattern_text verbatim (no prefix — intent patterns are short
       canonical strings).
    3. UPDATE embedding.
    4. Best-effort: flush Redis keys matching intent_emb:* so the live
       message-embedding cache (1-hour TTL) doesn't serve stale OLD-model
       results compared against NEW-model patterns.

Operational order (matches the Phase 4 runbook):
  - Deploy code with OPENAI_EMBEDDING_MODEL env still at the OLD value
    (services unchanged; new constants just read from env).
  - In staging/prod, pause new ingestion.
  - Run this script:
        python scripts/reembed_chunks.py --target both
  - Flip OPENAI_EMBEDDING_MODEL=<new> across all services and restart.
  - Resume ingestion.

Usage:
  # Chunks only (default — backward compatible)
  VECTOR_DATABASE_URL=postgresql://... OPENAI_API_KEY=sk-... \\
      python scripts/reembed_chunks.py --dry-run

  # Intents only (requires WORKFLOW_DATABASE_URL or override)
  python scripts/reembed_chunks.py --target intents

  # Both, single tenant first to validate
  python scripts/reembed_chunks.py --target both --tenant-id <id>

  # Full migration in one shot
  python scripts/reembed_chunks.py --target both \\
      --target-model text-embedding-3-small
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    sys.stderr.write("openai package not installed. pip install openai\n")
    sys.exit(2)

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:
    sys.stderr.write("sqlalchemy not installed. pip install sqlalchemy\n")
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--target",
        choices=["chunks", "intents", "both"],
        default="chunks",
        help=("Which table to re-embed. 'chunks' (default) = "
              "vectors.document_chunks. 'intents' = "
              "workflow_intent_embeddings in workflow_db. 'both' = run "
              "chunks first, then intents."),
    )
    p.add_argument(
        "--target-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model to use for the re-embed.",
    )
    p.add_argument(
        "--tenant-id",
        default=None,
        help="Re-embed only this tenant. Defaults to all tenants.",
    )
    p.add_argument(
        "--workflow-database-url",
        default=None,
        help=("Optional WORKFLOW_DATABASE_URL override. Falls back to env "
              "var, then to deriving workflow_db from VECTOR_DATABASE_URL."),
    )
    p.add_argument(
        "--skip-cache-flush",
        action="store_true",
        help=("Skip flushing intent_emb:* Redis keys after re-embedding "
              "intents. By default the cache IS flushed so stale OLD-model "
              "message embeddings don't sit in cache for an hour."),
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Number of rows to embed per OpenAI request (default 64).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows and preview embed-text, do not call OpenAI or UPDATE.",
    )
    p.add_argument(
        "--sleep-ms",
        type=int,
        default=0,
        help="Sleep this many ms between batches (rate-limit cushion).",
    )
    p.add_argument(
        "--max-rows",
        "--max-chunks",  # alias for backward compat
        dest="max_rows",
        type=int,
        default=0,
        help="Cap total rows processed per target (0 = no cap). Useful for testing.",
    )
    return p.parse_args()


def build_workflow_engine(override_url: Optional[str]) -> Engine:
    """Build an SQLAlchemy engine pointing at workflow_db.

    Resolution order:
      1. --workflow-database-url CLI arg
      2. WORKFLOW_DATABASE_URL env var
      3. Derive from VECTOR_DATABASE_URL by swapping the trailing /vector_db
         path component with /workflow_db (covers local dev).
    """
    url = override_url or os.environ.get("WORKFLOW_DATABASE_URL")
    if not url:
        vec_url = os.environ.get("VECTOR_DATABASE_URL", "")
        if "/vector_db" in vec_url:
            url = vec_url.replace("/vector_db", "/workflow_db")
        else:
            sys.stderr.write(
                "Could not resolve workflow_db URL. Set WORKFLOW_DATABASE_URL "
                "or pass --workflow-database-url. (Tried deriving from "
                "VECTOR_DATABASE_URL but no /vector_db substring found.)\n"
            )
            sys.exit(2)
    return create_engine(url, pool_pre_ping=True)


def build_engine() -> Engine:
    url = os.environ.get("VECTOR_DATABASE_URL")
    if not url:
        sys.stderr.write(
            "VECTOR_DATABASE_URL env var is required. "
            "Example: postgresql://postgres:password@localhost:5432/vector_db\n"
        )
        sys.exit(2)
    return create_engine(url, pool_pre_ping=True)


def get_openai_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.stderr.write("OPENAI_API_KEY env var is required.\n")
        sys.exit(2)
    return OpenAI(api_key=key, timeout=60.0, max_retries=2)


def count_chunks(engine: Engine, tenant_id: Optional[str]) -> int:
    sql = "SELECT COUNT(*) AS c FROM vectors.document_chunks"
    params = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


def iter_chunks(
    engine: Engine,
    tenant_id: Optional[str],
    batch_size: int,
    max_rows: int,
):
    """
    Yield (id, embed_text) batches. Cursor-style: orders by id and pages with
    a 'id > :last' keyset so we tolerate concurrent inserts and don't get
    stuck on offset performance.
    """
    base_sql = """
        SELECT id, content, section_title
        FROM vectors.document_chunks
        WHERE id > :last
          {tenant_clause}
        ORDER BY id ASC
        LIMIT :limit
    """
    tenant_clause = ""
    params_base = {}
    if tenant_id:
        tenant_clause = "AND tenant_id = :tid"
        params_base["tid"] = tenant_id

    sql = base_sql.format(tenant_clause=tenant_clause)
    last_id = ""
    processed = 0
    while True:
        if max_rows and processed >= max_rows:
            return
        remaining = (max_rows - processed) if max_rows else batch_size
        chunk_size = min(batch_size, remaining) if max_rows else batch_size

        with engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {**params_base, "last": last_id, "limit": chunk_size},
            ).fetchall()

        if not rows:
            return

        batch: List[Tuple[str, str]] = []
        for row in rows:
            section_title = (row.section_title or "").strip()
            content = row.content or ""
            embed_text = f"{section_title}\n\n{content}" if section_title else content
            batch.append((row.id, embed_text))
            last_id = row.id

        processed += len(batch)
        yield batch


def update_embeddings(
    engine: Engine,
    items: List[Tuple[str, List[float]]],
) -> None:
    """UPDATE one batch of (chunk_id, embedding) pairs."""
    update_sql = text(
        "UPDATE vectors.document_chunks SET embedding = :embedding, updated_at = NOW() "
        "WHERE id = :id"
    )
    with engine.begin() as conn:
        for cid, emb in items:
            conn.execute(update_sql, {"id": cid, "embedding": str(emb)})


# ---------------------------------------------------------------- intents leg

def count_intents(engine: Engine, tenant_id: Optional[str]) -> int:
    sql = "SELECT COUNT(*) AS c FROM workflow_intent_embeddings"
    params = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


def iter_intents(
    engine: Engine,
    tenant_id: Optional[str],
    batch_size: int,
    max_rows: int,
):
    """
    Yield (id, pattern_text) batches from workflow_intent_embeddings.
    Same keyset pagination pattern as iter_chunks().
    """
    base_sql = """
        SELECT id, pattern_text
        FROM workflow_intent_embeddings
        WHERE id > :last
          {tenant_clause}
        ORDER BY id ASC
        LIMIT :limit
    """
    tenant_clause = ""
    params_base = {}
    if tenant_id:
        tenant_clause = "AND tenant_id = :tid"
        params_base["tid"] = tenant_id

    sql = base_sql.format(tenant_clause=tenant_clause)
    last_id = ""
    processed = 0
    while True:
        if max_rows and processed >= max_rows:
            return
        remaining = (max_rows - processed) if max_rows else batch_size
        chunk_size = min(batch_size, remaining) if max_rows else batch_size

        with engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {**params_base, "last": last_id, "limit": chunk_size},
            ).fetchall()

        if not rows:
            return

        batch: List[Tuple[str, str]] = []
        for row in rows:
            # Pattern text is embedded verbatim — no section_title concept here.
            batch.append((row.id, row.pattern_text or ""))
            last_id = row.id

        processed += len(batch)
        yield batch


def update_intent_embeddings(
    engine: Engine,
    items: List[Tuple[str, List[float]]],
) -> None:
    """UPDATE one batch of (id, embedding) pairs in workflow_intent_embeddings."""
    update_sql = text(
        "UPDATE workflow_intent_embeddings SET embedding = :embedding WHERE id = :id"
    )
    with engine.begin() as conn:
        for rid, emb in items:
            conn.execute(update_sql, {"id": rid, "embedding": str(emb)})


def flush_intent_emb_cache() -> int:
    """
    Best-effort: delete intent_emb:* keys from Redis.

    Intent-matching caches per-message embeddings under intent_emb:{md5(msg)}
    with a 1-hour TTL. The cache key does NOT include the model name, so
    after flipping OPENAI_EMBEDDING_MODEL the cache will serve OLD-model
    embeddings for an hour, causing intent_match degradation.

    Returns:
        Number of keys deleted, or -1 if Redis is unavailable / not configured.
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis  # type: ignore
    except ImportError:
        sys.stderr.write(
            "  (redis package not installed — skipping cache flush. "
            "pip install redis or use --skip-cache-flush to silence this.)\n"
        )
        return -1
    try:
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
    except Exception as e:
        sys.stderr.write(f"  (redis unavailable at {redis_url}: {e})\n")
        return -1

    deleted = 0
    for key in client.scan_iter(match="intent_emb:*", count=500):
        try:
            deleted += int(client.delete(key) or 0)
        except Exception:
            pass
    return deleted


def _process_target(
    label: str,
    engine: Engine,
    count_fn,
    iter_fn,
    update_fn,
    args: argparse.Namespace,
    client: Optional[OpenAI],
) -> int:
    """
    Generic re-embed pump. `iter_fn` yields batches of (id, text_to_embed).
    Returns count of rows processed (0 if nothing to do).
    """
    total = count_fn(engine, args.tenant_id)
    target_total = min(total, args.max_rows) if args.max_rows else total

    print(f"=== {label} ===")
    print(f"  database: {engine.url.database} on {engine.url.host}:{engine.url.port}")
    print(f"  rows in scope: {target_total}  (DB total for this filter: {total})")

    if target_total == 0:
        print("  Nothing to do.\n")
        return 0

    processed = 0
    batches = 0
    start = time.time()
    for batch in iter_fn(engine, args.tenant_id, args.batch_size, args.max_rows):
        batches += 1
        ids = [rid for rid, _ in batch]
        texts = [t for _, t in batch]

        if args.dry_run:
            preview = texts[0][:80].replace("\n", " ") if texts else ""
            print(f"  [dry-run] batch {batches}: {len(batch)} rows; "
                  f"first id={ids[0]}; first text preview: {preview!r}")
        else:
            assert client is not None
            try:
                resp = client.embeddings.create(model=args.target_model, input=texts)
            except Exception as e:
                sys.stderr.write(
                    f"OpenAI request failed at batch {batches} "
                    f"(last_id={ids[-1]}): {e}\n"
                )
                raise
            embeddings = [item.embedding for item in resp.data]
            update_fn(engine, list(zip(ids, embeddings)))

        processed += len(batch)
        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0.0
        print(
            f"  batch {batches}: processed {processed}/{target_total} "
            f"({100.0 * processed / target_total:.1f}%, {rate:.1f} rows/s)"
        )

        if args.sleep_ms and not args.dry_run:
            time.sleep(args.sleep_ms / 1000.0)

    elapsed = time.time() - start
    print(f"  Done {label.lower()}: {processed} rows in {elapsed:.1f}s "
          f"({processed / elapsed:.1f} rows/s).\n")
    return processed


def main() -> int:
    args = parse_args()

    print(f"Target model: {args.target_model}")
    print(f"Tenant filter: {args.tenant_id or '(all tenants)'}")
    print(f"Targets: {args.target}")
    print(f"Batch size: {args.batch_size}  Sleep between batches: {args.sleep_ms}ms")
    print(f"Dry-run: {args.dry_run}")
    print()

    client: Optional[OpenAI] = None if args.dry_run else get_openai_client()

    do_chunks = args.target in ("chunks", "both")
    do_intents = args.target in ("intents", "both")

    if do_chunks:
        chunks_engine = build_engine()
        try:
            _process_target(
                "CHUNKS (vectors.document_chunks)",
                chunks_engine,
                count_chunks,
                iter_chunks,
                update_embeddings,
                args,
                client,
            )
        except Exception as e:
            sys.stderr.write(f"Chunks pass failed: {e}\n")
            return 3

    if do_intents:
        intents_engine = build_workflow_engine(args.workflow_database_url)
        try:
            processed = _process_target(
                "INTENTS (workflow_intent_embeddings)",
                intents_engine,
                count_intents,
                iter_intents,
                update_intent_embeddings,
                args,
                client,
            )
        except Exception as e:
            sys.stderr.write(f"Intents pass failed: {e}\n")
            return 3

        # Cache flush — only meaningful if we actually re-embedded patterns.
        if processed > 0 and not args.dry_run and not args.skip_cache_flush:
            print("Flushing Redis intent_emb:* cache (stale OLD-model entries)...")
            deleted = flush_intent_emb_cache()
            if deleted >= 0:
                print(f"  Deleted {deleted} cache entries.\n")
        elif args.dry_run and do_intents:
            print("(dry-run) Skipping Redis cache flush.\n")
        elif args.skip_cache_flush and do_intents:
            print("(--skip-cache-flush) Leaving intent_emb:* cache intact. "
                  "Live message embeddings may be stale for up to 1h.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
