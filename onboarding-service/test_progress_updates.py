#!/usr/bin/env python3
"""
Test script to verify website scraping progress updates are returned correctly to the UI
"""
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_db
from app.services.website_scraper import WebsiteScraper

async def test_progress_updates():
    """Test progress updates during website scraping"""

    # Get database session
    db = next(get_db())

    try:
        # Start a new ingestion
        tenant_id = "9eb23c01-b66a-4e23-8316-4884532d5b04"
        website_url = "https://nigerianports.gov.ng/"

        scraper = WebsiteScraper(db, use_javascript=True)

        # Start ingestion
        print(f"Starting ingestion for {website_url}...")
        ingestion = scraper.start_website_ingestion(tenant_id, website_url)
        print(f"✅ Ingestion started with ID: {ingestion.id}")
        print(f"   Initial status: {ingestion.status}")
        print(f"   Pages discovered: {ingestion.pages_discovered}")
        print(f"   Pages processed: {ingestion.pages_processed}")
        print(f"   Pages failed: {ingestion.pages_failed}")
        print()

        # Start processing in background
        print("Starting background processing...")
        print("Monitoring progress updates every 30 seconds for 3 minutes...")
        print("=" * 80)

        # Create a task to process the ingestion
        processing_task = asyncio.create_task(scraper.process_existing_ingestion(ingestion))

        # Monitor progress for 3 minutes
        for i in range(6):  # 6 checks over 3 minutes
            await asyncio.sleep(30)  # Wait 30 seconds

            # Refresh ingestion from database
            db.refresh(ingestion)

            print(f"\n⏰ Progress Update #{i+1} (after {(i+1)*30} seconds):")
            print(f"   Status: {ingestion.status}")
            print(f"   Pages discovered: {ingestion.pages_discovered}")
            print(f"   Pages processed: {ingestion.pages_processed}")
            print(f"   Pages failed: {ingestion.pages_failed}")
            print(f"   Progress: {ingestion.pages_processed}/{ingestion.pages_discovered} pages")

            # Format as JSON response (UI format)
            json_format = {
                "id": ingestion.id,
                "base_url": ingestion.base_url,
                "status": ingestion.status.value if hasattr(ingestion.status, 'value') else str(ingestion.status),
                "pages_discovered": ingestion.pages_discovered,
                "pages_processed": ingestion.pages_processed,
                "pages_failed": ingestion.pages_failed,
                "started_at": ingestion.started_at.isoformat() if ingestion.started_at else None,
                "completed_at": ingestion.completed_at.isoformat() if ingestion.completed_at else None,
                "error_message": ingestion.error_message
            }
            print(f"\n   JSON Response Format:")
            import json
            print(f"   {json.dumps(json_format, indent=2)}")

            # Check if completed
            if ingestion.status in ["completed", "failed"]:
                print(f"\n✅ Ingestion {ingestion.status}!")
                break

        print("\n" + "=" * 80)
        print("Progress monitoring complete!")

        # Wait for processing to complete
        if not processing_task.done():
            print("Waiting for scraping to complete...")
            await processing_task

        # Final status
        db.refresh(ingestion)
        print(f"\n📊 Final Status:")
        print(f"   Status: {ingestion.status}")
        print(f"   Pages discovered: {ingestion.pages_discovered}")
        print(f"   Pages processed: {ingestion.pages_processed}")
        print(f"   Pages failed: {ingestion.pages_failed}")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_progress_updates())
