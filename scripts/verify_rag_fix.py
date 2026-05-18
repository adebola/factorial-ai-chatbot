#!/usr/bin/env python3
"""
RAG-fix verification: report whether Phases 2-5 are visible in the vector DB
for a given tenant.

What this checks (DB-level — does NOT call the chat service):
  * Migration:        content_tsv column + GIN indexes exist.
  * Phase 2 coverage: percentage of the tenant's chunks that have
                      section_title populated (HTML-aware chunker output).
  * Phase 3 coverage: lexical hit counts for a configurable keyword list.
  * Phase 4 hint:     prints the most recent updated_at timestamp on a chunk
                      to suggest whether a re-embed has been run lately
                      (semantic distance has to be checked via the chat API).

Designed as a quick "did the re-ingest land?" smoke test after Phase 5.

Usage:
  VECTOR_DATABASE_URL=postgresql://... \\
      python scripts/verify_rag_fix.py --tenant-id <id>

  # Override the keyword list (comma-separated). Default targets Emobile's
  # actual "Join Our Team" section vocabulary.
  python scripts/verify_rag_fix.py --tenant-id <id> \\
      --keywords "careers,jobs,hiring,embryologist,nurse"
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from sqlalchemy import create_engine, text
except ImportError:
    sys.stderr.write("sqlalchemy not installed. pip install sqlalchemy\n")
    sys.exit(2)


DEFAULT_KEYWORDS = [
    # Direct words a user might type
    "careers", "jobs", "hiring", "career", "opportunities", "vacancies",
    # Specific roles in Emobile's "Join Our Team" section
    "embryologist", "nurse", "pharmacist", "laboratory technician",
    # Heading phrasing actually on the page
    "join our team", "team",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tenant-id", required=True, help="Tenant ID to verify")
    p.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated keywords to run lexical-hit checks against.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    url = os.environ.get("VECTOR_DATABASE_URL")
    if not url:
        sys.stderr.write("VECTOR_DATABASE_URL env var is required\n")
        return 2
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    engine = create_engine(url, pool_pre_ping=True)
    tid = args.tenant_id

    with engine.connect() as conn:
        # ----- 1. Migration sanity ----------------------------------------
        col_row = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='vectors' AND table_name='document_chunks' "
            "  AND column_name='content_tsv'"
        )).fetchone()
        idx_rows = conn.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='vectors' AND tablename='document_chunks' "
            "  AND indexname LIKE '%tsv%'"
        )).fetchall()
        idx_names = [r.indexname for r in idx_rows]

        print("=" * 64)
        print(f"RAG verification for tenant {tid}")
        print("=" * 64)
        print()
        print("Migration (Phase 3):")
        print(f"  content_tsv column present : {'YES' if col_row else 'NO'}")
        print(f"  GIN indexes                : {idx_names or '(none)'}")
        if not col_row or not idx_names:
            print("  >>> Migration not fully applied; run db-init/09-add-fulltext-to-chunks.sql")

        # ----- 2. Chunk counts + section coverage -------------------------
        cov = conn.execute(text("""
            SELECT
              COUNT(*)                                      AS total,
              COUNT(*) FILTER (WHERE section_title IS NOT NULL AND section_title <> '') AS with_section,
              COUNT(DISTINCT source_name)                   AS distinct_sources,
              MAX(updated_at)                               AS last_updated
            FROM vectors.document_chunks
            WHERE tenant_id = :tid
        """), {"tid": tid}).fetchone()

        total = int(cov.total or 0)
        with_section = int(cov.with_section or 0)
        section_pct = (100.0 * with_section / total) if total else 0.0
        print()
        print("Chunks in vector store (Phase 2 / Phase 5):")
        print(f"  total                        : {total}")
        print(f"  with section_title           : {with_section} ({section_pct:.1f}%)")
        print(f"  distinct source_name values  : {cov.distinct_sources or 0}")
        print(f"  last updated_at              : {cov.last_updated}")
        if total == 0:
            print("  >>> Tenant has no chunks; re-ingest before re-running this check")
            return 1
        if section_pct < 25.0:
            print("  >>> Very few chunks carry section_title — Phase 2 (HTML-aware")
            print("      chunker) likely hasn't been applied to this tenant yet.")
            print("      Re-ingest with the new code, or accept that PDFs/DOCX won't")
            print("      have section_title (heading detection isn't implemented for")
            print("      those source types).")

        # ----- 3. Section_title cardinality (top headings) ----------------
        if with_section > 0:
            top = conn.execute(text("""
                SELECT section_title, COUNT(*) AS c
                FROM vectors.document_chunks
                WHERE tenant_id = :tid
                  AND section_title IS NOT NULL AND section_title <> ''
                GROUP BY section_title
                ORDER BY c DESC
                LIMIT 12
            """), {"tid": tid}).fetchall()
            print()
            print("Top sections (Phase 5):")
            for row in top:
                preview = (row.section_title or "")[:70]
                print(f"  {row.c:>4}  {preview}")

        # ----- 4. Lexical hit counts (Phase 3) ----------------------------
        print()
        print("Lexical hit counts (Phase 3) — chunks matching plainto_tsquery:")
        zero_hit_terms = []
        for kw in keywords:
            row = conn.execute(text("""
                SELECT COUNT(*) AS c FROM vectors.document_chunks
                WHERE tenant_id = :tid
                  AND content_tsv @@ plainto_tsquery('english', :q)
            """), {"tid": tid, "q": kw}).fetchone()
            c = int(row.c if row else 0)
            marker = "✓" if c > 0 else "·"
            print(f"  {marker} {kw!r:32} → {c}")
            if c == 0:
                zero_hit_terms.append(kw)

        if zero_hit_terms:
            print()
            print("  Note: zero-hit terms ({}) are either truly absent from the".format(
                ", ".join(zero_hit_terms)
            ))
            print("  source content OR multi-word terms with stricter AND semantics")
            print("  in plainto_tsquery. After Phase 2 re-ingest the section_title")
            print("  prefix ('Join Our Team' etc.) joins the embedding text, so")
            print("  vector retrieval catches phrasing the lexical leg can't.")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
