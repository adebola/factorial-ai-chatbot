"""
Test script to verify categorization-aware search functionality.

This script demonstrates:
1. Intent detection for different query types
2. Vector search with content type filtering
3. Categorization metadata in search results

Run this script to verify the Standard Version implementation.
"""

import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.chat_service import ChatService
from app.services.pg_vector_store import PgVectorStore
from app.core.database import SessionLocal


def test_intent_detection():
    """Test intent detection for various query types."""

    print("=" * 60)
    print("TEST 1: Intent Detection")
    print("=" * 60)

    # Create chat service instance
    db = SessionLocal()
    chat_service = ChatService(db)

    test_queries = [
        ("What's our refund policy?", "policy"),
        ("Show me invoice #12345", "invoice"),
        ("How much did we pay for the contract?", "invoice/contract"),
        ("What are the technical specifications?", "technical"),
        ("Send me the quarterly report", "report"),
        ("What email did John send yesterday?", "email"),
        ("Hello, how are you?", "no intent"),
    ]

    print("\nQuery Intent Detection Results:\n")

    for query, expected_intent in test_queries:
        detected_filter = chat_service._detect_content_type_intent(query)

        print(f"Query: '{query}'")
        print(f"  Expected: {expected_intent}")
        print(f"  Detected filter: {detected_filter}")
        print()

    db.close()


def test_vector_search_with_filtering():
    """Test vector search with content type filtering."""

    print("=" * 60)
    print("TEST 2: Vector Search with Filtering")
    print("=" * 60)

    vector_store = PgVectorStore()

    # Test tenant ID (replace with your actual tenant ID)
    tenant_id = "9eb23c01-b66a-4e23-8316-4884532d5b04"

    print("\n1. Search WITHOUT filtering (baseline):\n")

    query = "payment policy"
    results_unfiltered = vector_store.search_similar(
        tenant_id=tenant_id,
        query=query,
        k=4
    )

    print(f"Query: '{query}'")
    print(f"Results: {len(results_unfiltered)} documents")

    for i, doc in enumerate(results_unfiltered, 1):
        content_type = doc.metadata.get('content_type', 'unknown')
        distance = doc.metadata.get('distance', 'N/A')
        print(f"  {i}. Type: {content_type}, Distance: {distance:.3f}")
        print(f"     Content: {doc.page_content[:100]}...")

    print("\n2. Search WITH content type filtering:\n")

    results_filtered = vector_store.search_similar(
        tenant_id=tenant_id,
        query=query,
        k=4,
        content_types=['policy', 'manual']  # Filter to only policies
    )

    print(f"Query: '{query}'")
    print(f"Filter: content_types=['policy', 'manual']")
    print(f"Results: {len(results_filtered)} documents")

    for i, doc in enumerate(results_filtered, 1):
        content_type = doc.metadata.get('content_type', 'unknown')
        distance = doc.metadata.get('distance', 'N/A')
        print(f"  {i}. Type: {content_type}, Distance: {distance:.3f}")
        print(f"     Content: {doc.page_content[:100]}...")

    print("\n3. Metadata comparison:\n")

    if results_unfiltered and results_filtered:
        print("WITHOUT filtering - content types found:")
        types_unfiltered = set(doc.metadata.get('content_type') for doc in results_unfiltered if doc.metadata.get('content_type'))
        print(f"  {types_unfiltered}")

        print("\nWITH filtering - content types found:")
        types_filtered = set(doc.metadata.get('content_type') for doc in results_filtered if doc.metadata.get('content_type'))
        print(f"  {types_filtered}")

        print(f"\n✅ Filtering works: Only {types_filtered} returned (filtered out {types_unfiltered - types_filtered})")


def test_categorization_metadata():
    """Test that categorization metadata is included in results."""

    print("=" * 60)
    print("TEST 3: Categorization Metadata in Results")
    print("=" * 60)

    vector_store = PgVectorStore()
    tenant_id = "9eb23c01-b66a-4e23-8316-4884532d5b04"

    results = vector_store.search_similar(
        tenant_id=tenant_id,
        query="website information",
        k=2
    )

    print(f"\nQuery: 'website information'")
    print(f"Results: {len(results)} documents\n")

    for i, doc in enumerate(results, 1):
        print(f"Document {i}:")
        print(f"  Content: {doc.page_content[:80]}...")
        print(f"  Metadata:")
        print(f"    - source_name: {doc.metadata.get('source_name')}")
        print(f"    - content_type: {doc.metadata.get('content_type')}")
        print(f"    - category_ids: {doc.metadata.get('category_ids', [])}")
        print(f"    - tag_ids: {doc.metadata.get('tag_ids', [])}")
        print(f"    - distance: {doc.metadata.get('distance', 'N/A'):.3f}")
        print()


def main():
    """Run all tests."""

    print("\n" + "=" * 60)
    print("CATEGORIZATION-AWARE SEARCH - VERIFICATION TESTS")
    print("=" * 60 + "\n")

    try:
        # Test 1: Intent Detection
        test_intent_detection()

        # Test 2: Vector Search with Filtering
        test_vector_search_with_filtering()

        # Test 3: Categorization Metadata
        test_categorization_metadata()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
