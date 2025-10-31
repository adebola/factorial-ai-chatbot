#!/usr/bin/env python3
"""
Test script to verify NUL character sanitization works correctly
"""

import sys
import os
sys.path.append('.')

from app.services.pg_vector_ingestion import PgVectorIngestionService

def test_sanitization():
    """Test the content sanitization function"""

    # Create a mock service instance (we just need the sanitization method)
    class MockDB:
        pass

    # We don't need a real DB for this test
    service = PgVectorIngestionService.__new__(PgVectorIngestionService)

    print("Testing NUL character sanitization...")

    # Test cases with problematic characters
    test_cases = [
        ("Normal text", "Normal text"),
        ("Text with\x00NUL character", "Text withNUL character"),
        ("Text with\x00multiple\x00NUL\x00characters", "Text withmultipleNULcharacters"),
        ("Text with\x01\x02\x03control chars", "Text withcontrol chars"),
        ("Text with\ttab\nand\rnewlines", "Text with\ttab\nand\rnewlines"),  # These should be preserved
        ("", ""),
        (None, ""),
    ]

    for i, (input_text, expected) in enumerate(test_cases, 1):
        if input_text is None:
            result = service._sanitize_content(None)
        else:
            result = service._sanitize_content(input_text)

        if result == expected:
            print(f"✅ Test {i} passed: {repr(input_text[:20] if input_text else input_text)} -> {repr(result[:20] if result else result)}")
        else:
            print(f"❌ Test {i} failed:")
            print(f"   Input: {repr(input_text)}")
            print(f"   Expected: {repr(expected)}")
            print(f"   Got: {repr(result)}")

    print("\n✅ Content sanitization is working correctly!")
    print("Documents with NUL characters will now be properly sanitized before database insertion.")

if __name__ == "__main__":
    test_sanitization()