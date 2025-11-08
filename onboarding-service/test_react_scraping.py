"""
Test script to verify React SPA scraping with AUTO strategy after Playwright installation.
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.website_scraper import WebsiteScraper

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/onboard_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def test_react_spa_scraping():
    """Test scraping of React SPA website"""

    print("=" * 80)
    print("Testing React SPA Scraping with AUTO Strategy")
    print("=" * 80)
    print()

    # Create database session
    db = SessionLocal()

    try:
        # Create scraper instance (no use_javascript parameter - uses AUTO strategy)
        scraper = WebsiteScraper(db)

        # Test URL - React SPA that requires JavaScript
        test_url = "https://www.brookehowseestate.com/"

        print(f"🌐 Testing URL: {test_url}")
        print(f"📋 Strategy: {scraper.strategy} (should be 'auto')")
        print()

        # Scrape the page
        print("🚀 Starting scrape...")
        print("-" * 80)

        document = await scraper._scrape_page_with_strategy(
            tenant_id="test-tenant",
            ingestion_id="test-ingestion",
            url=test_url
        )

        print("-" * 80)
        print()

        if document and document.page_content:
            content = document.page_content
            metadata = document.metadata
            print("✅ SUCCESS! Content extracted:")
            print(f"   - Content length: {len(content)} characters")
            print(f"   - Method used: {metadata.get('scrape_method', 'unknown')}")
            print(f"   - Used JavaScript: {metadata.get('used_javascript', False)}")
            print()
            print("📄 First 500 characters of content:")
            print("-" * 80)
            print(content[:500])
            print("-" * 80)
            print()

            # Check if this was actually rendered content (not the minimal React shell)
            if len(content) > 1000 and "JavaScript" not in content[:100]:
                print("✅ VERIFICATION PASSED: Full content extracted (not minimal React shell)")
            elif "JavaScript" in content[:100]:
                print("❌ VERIFICATION FAILED: Still getting React shell requiring JavaScript")
            else:
                print("⚠️  WARNING: Content seems short, may need investigation")
        else:
            print("❌ FAILED: No content extracted")
            print(f"   - Metadata: {metadata}")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

    print()
    print("=" * 80)
    print("Test Complete")
    print("=" * 80)

if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_react_spa_scraping())
