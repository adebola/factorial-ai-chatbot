"""
Backfill script to populate file_size for existing documents.

This script updates Document records that have NULL file_size values by fetching
the actual file sizes from MinIO storage.

Usage:
    python backfill_document_file_sizes.py [--tenant-id TENANT_ID] [--dry-run]

Arguments:
    --tenant-id: Optional tenant ID to filter documents (default: all tenants)
    --dry-run: Show what would be updated without making changes

Example:
    # Backfill all documents
    python backfill_document_file_sizes.py

    # Backfill for specific tenant
    python backfill_document_file_sizes.py --tenant-id abc-123

    # Preview changes without updating
    python backfill_document_file_sizes.py --dry-run
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.models.tenant import Document
from app.services.storage_service import StorageService
from app.core.database import get_db
from app.core.logging_config import get_logger

logger = get_logger("backfill_file_sizes")


def backfill_document_file_sizes(tenant_id: str = None, dry_run: bool = False):
    """
    Backfill file_size for documents with NULL values.

    Args:
        tenant_id: Optional tenant ID to filter documents
        dry_run: If True, show what would be updated without making changes
    """
    logger.info("Starting file size backfill", tenant_id=tenant_id, dry_run=dry_run)

    db = next(get_db())
    storage_service = StorageService()

    try:
        # Get documents with NULL file_size
        query = db.query(Document).filter(Document.file_size.is_(None))

        if tenant_id:
            query = query.filter(Document.tenant_id == tenant_id)

        documents = query.all()

        logger.info(f"Found {len(documents)} documents with NULL file_size")

        if len(documents) == 0:
            print("✅ No documents need backfilling. All documents have file_size set.")
            return

        # Statistics
        stats = {
            "total": len(documents),
            "updated": 0,
            "file_not_found": 0,
            "errors": 0,
            "total_bytes": 0
        }

        # Process each document
        for idx, doc in enumerate(documents, 1):
            try:
                print(f"\n[{idx}/{len(documents)}] Processing document: {doc.id}")
                print(f"  Filename: {doc.original_filename}")
                print(f"  File path: {doc.file_path}")
                print(f"  Tenant: {doc.tenant_id}")

                if not doc.file_path:
                    print(f"  ⚠️  No file_path - setting file_size to 0")
                    if not dry_run:
                        doc.file_size = 0
                        db.commit()
                    stats["file_not_found"] += 1
                    continue

                # Get object metadata from MinIO
                try:
                    stat = storage_service.client.stat_object(
                        storage_service.bucket_name,
                        doc.file_path
                    )

                    file_size = stat.size
                    print(f"  ✅ Found in MinIO: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")

                    if not dry_run:
                        doc.file_size = file_size
                        db.commit()

                    stats["updated"] += 1
                    stats["total_bytes"] += file_size

                except Exception as e:
                    # File not found in MinIO - set to 0
                    print(f"  ⚠️  File not found in MinIO: {e}")
                    print(f"  Setting file_size to 0")

                    if not dry_run:
                        doc.file_size = 0
                        db.commit()

                    stats["file_not_found"] += 1

            except Exception as e:
                print(f"  ❌ Error processing document: {e}")
                stats["errors"] += 1
                db.rollback()

        # Print summary
        print("\n" + "="*70)
        print("BACKFILL SUMMARY")
        print("="*70)
        print(f"Total documents processed: {stats['total']}")
        print(f"Successfully updated: {stats['updated']}")
        print(f"Files not found (set to 0): {stats['file_not_found']}")
        print(f"Errors: {stats['errors']}")
        print(f"Total storage found: {stats['total_bytes']:,} bytes ({stats['total_bytes'] / (1024*1024):.2f} MB)")

        if dry_run:
            print("\n⚠️  DRY RUN MODE - No changes were made to the database")
            print("Run without --dry-run to apply changes")
        else:
            print("\n✅ Backfill completed successfully")

        logger.info("File size backfill completed", stats=stats, dry_run=dry_run)

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        print(f"\n❌ Backfill failed: {e}")
        db.rollback()
        raise

    finally:
        db.close()


def main():
    """Main entry point for the backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill file_size for documents with NULL values",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Filter documents by tenant ID (default: all tenants)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )

    args = parser.parse_args()

    print("="*70)
    print("DOCUMENT FILE SIZE BACKFILL SCRIPT")
    print("="*70)
    print(f"Tenant filter: {args.tenant_id or 'ALL TENANTS'}")
    print(f"Mode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE (will update database)'}")
    print("="*70 + "\n")

    if not args.dry_run:
        confirmation = input("⚠️  This will modify the database. Continue? [y/N]: ")
        if confirmation.lower() != 'y':
            print("Aborted by user")
            return

    backfill_document_file_sizes(tenant_id=args.tenant_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
