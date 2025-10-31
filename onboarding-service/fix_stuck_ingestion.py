#!/usr/bin/env python3
"""
Fix stuck website ingestion by calculating actual status from website_pages table
"""
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_db
from app.models.tenant import WebsiteIngestion, WebsitePage, IngestionStatus, DocumentStatus
from sqlalchemy import func
from datetime import datetime

def fix_ingestion(ingestion_id: str):
    """Fix a stuck ingestion by recalculating stats from pages table"""

    db = next(get_db())

    try:
        # Get the ingestion
        ingestion = db.query(WebsiteIngestion).filter(
            WebsiteIngestion.id == ingestion_id
        ).first()

        if not ingestion:
            print(f"❌ Ingestion {ingestion_id} not found")
            return False

        print(f"Found ingestion: {ingestion.base_url}")
        print(f"Current status: {ingestion.status}")
        print(f"Current pages_discovered: {ingestion.pages_discovered}")
        print(f"Current pages_processed: {ingestion.pages_processed}")
        print(f"Current pages_failed: {ingestion.pages_failed}")
        print()

        # Get actual stats from website_pages table
        pages_stats = db.query(
            func.count(WebsitePage.id).label('total'),
            func.count(func.nullif(WebsitePage.status == DocumentStatus.COMPLETED, False)).label('completed'),
            func.count(func.nullif(WebsitePage.status == DocumentStatus.FAILED, False)).label('failed')
        ).filter(
            WebsitePage.ingestion_id == ingestion_id
        ).first()

        total_pages = pages_stats.total
        completed_pages = db.query(WebsitePage).filter(
            WebsitePage.ingestion_id == ingestion_id,
            WebsitePage.status == DocumentStatus.COMPLETED
        ).count()

        failed_pages = db.query(WebsitePage).filter(
            WebsitePage.ingestion_id == ingestion_id,
            WebsitePage.status == DocumentStatus.FAILED
        ).count()

        processing_pages = db.query(WebsitePage).filter(
            WebsitePage.ingestion_id == ingestion_id,
            WebsitePage.status == DocumentStatus.PROCESSING
        ).count()

        print(f"Actual stats from website_pages table:")
        print(f"  Total pages: {total_pages}")
        print(f"  Completed: {completed_pages}")
        print(f"  Failed: {failed_pages}")
        print(f"  Still processing: {processing_pages}")
        print()

        # Update ingestion record
        ingestion.pages_discovered = total_pages
        ingestion.pages_processed = completed_pages
        ingestion.pages_failed = failed_pages

        # Determine status
        if processing_pages > 0:
            ingestion.status = IngestionStatus.IN_PROGRESS
            print("Status: IN_PROGRESS (some pages still processing)")
        elif completed_pages + failed_pages == total_pages and total_pages > 0:
            ingestion.status = IngestionStatus.COMPLETED
            ingestion.completed_at = datetime.now()
            print("Status: COMPLETED (all pages processed)")
        else:
            ingestion.status = IngestionStatus.FAILED
            ingestion.completed_at = datetime.now()
            ingestion.error_message = "Ingestion incomplete - processing interrupted"
            print("Status: FAILED (processing was interrupted)")

        db.commit()

        print()
        print("✅ Ingestion record updated successfully!")
        print(f"New status: {ingestion.status}")
        print(f"Pages discovered: {ingestion.pages_discovered}")
        print(f"Pages processed: {ingestion.pages_processed}")
        print(f"Pages failed: {ingestion.pages_failed}")

        return True

    except Exception as e:
        print(f"❌ Error fixing ingestion: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fix_stuck_ingestion.py <ingestion_id>")
        print()
        print("Example: python3 fix_stuck_ingestion.py 61562137-9519-4ec8-a3c1-226b72088e36")
        sys.exit(1)

    ingestion_id = sys.argv[1]
    fix_ingestion(ingestion_id)
