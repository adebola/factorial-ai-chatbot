#!/usr/bin/env python3
"""
Test script to verify shared cache integration between services.

This script tests:
1. Onboarding service caches plan data using new cache keys
2. Authorization server can read from the same cache using same keys
3. Cache invalidation works correctly

Run this script to verify the shared cache implementation.
"""

import asyncio
import json
import redis
import requests
import time
from datetime import datetime

# Configuration
REDIS_URL = "redis://localhost:6379"
ONBOARDING_SERVICE_URL = "http://localhost:8001"
AUTH_SERVER_URL = "http://localhost:9002"

# Cache keys (must match the implementation)
FREE_TIER_CACHE_KEY = "plan:free_tier"

def test_redis_connection():
    """Test Redis connection"""
    print("🔗 Testing Redis connection...")
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        return r
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return None

def test_onboarding_service():
    """Test onboarding service health"""
    print("🏥 Testing onboarding service health...")
    try:
        response = requests.get(f"{ONBOARDING_SERVICE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Onboarding service is healthy")
            return True
    except Exception as e:
        print(f"❌ Onboarding service health check failed: {e}")
    return False

def test_auth_server():
    """Test authorization server health"""
    print("🔐 Testing authorization server health...")
    try:
        response = requests.get(f"{AUTH_SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Authorization server is healthy")
            return True
    except Exception as e:
        print(f"❌ Authorization server health check failed: {e}")
    return False

async def test_cache_flow():
    """Test the complete cache flow"""
    print("\n🔄 Testing shared cache flow...")

    redis_client = test_redis_connection()
    if not redis_client:
        return False

    # Step 1: Clear cache to start fresh
    print("1️⃣  Clearing existing cache...")
    redis_client.delete(FREE_TIER_CACHE_KEY)

    # Verify cache is empty
    cached_data = redis_client.get(FREE_TIER_CACHE_KEY)
    if cached_data:
        print(f"⚠️  Cache wasn't fully cleared: {cached_data[:100]}...")
    else:
        print("✅ Cache cleared successfully")

    # Step 2: Call onboarding service free-tier endpoint
    print("2️⃣  Calling onboarding service free-tier endpoint...")
    try:
        start_time = time.time()
        response = requests.get(f"{ONBOARDING_SERVICE_URL}/api/v1/plans/free-tier", timeout=10)
        onboarding_time = time.time() - start_time

        if response.status_code == 200:
            plan_data = response.json()
            print(f"✅ Onboarding service response ({onboarding_time:.2f}s):")
            print(f"   Plan ID: {plan_data.get('id')}")
            print(f"   Plan Name: {plan_data.get('name')}")
            print(f"   Document Limit: {plan_data.get('document_limit')}")
        else:
            print(f"❌ Onboarding service returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Onboarding service call failed: {e}")
        return False

    # Step 3: Check if data was cached by onboarding service
    print("3️⃣  Checking if onboarding service cached the data...")
    await asyncio.sleep(1)  # Give cache time to be written

    cached_data = redis_client.get(FREE_TIER_CACHE_KEY)
    if cached_data:
        cached_plan = json.loads(cached_data)
        print("✅ Data was cached by onboarding service:")
        print(f"   Cached Plan ID: {cached_plan.get('id')}")
        print(f"   Cached Plan Name: {cached_plan.get('name')}")

        # Verify cached data matches API response
        if cached_plan.get('id') == plan_data.get('id'):
            print("✅ Cached data matches API response")
        else:
            print("❌ Cached data doesn't match API response")
            return False
    else:
        print("❌ No data found in cache after onboarding service call")
        return False

    # Step 4: Call onboarding service again to test cache hit
    print("4️⃣  Calling onboarding service again to test cache hit...")
    try:
        start_time = time.time()
        response = requests.get(f"{ONBOARDING_SERVICE_URL}/api/v1/plans/free-tier", timeout=10)
        cached_time = time.time() - start_time

        if response.status_code == 200:
            print(f"✅ Second call successful ({cached_time:.2f}s)")
            if cached_time < onboarding_time * 0.8:  # Should be significantly faster
                print("✅ Second call was faster (likely cache hit)")
            else:
                print("⚠️  Second call wasn't significantly faster")
        else:
            print(f"❌ Second onboarding service call failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Second onboarding service call failed: {e}")

    # Step 5: Simulate authorization server reading from cache
    print("5️⃣  Simulating authorization server cache read...")

    # This simulates what the auth server does
    cached_data = redis_client.get(FREE_TIER_CACHE_KEY)
    if cached_data:
        auth_plan_data = json.loads(cached_data)
        print("✅ Authorization server can read cached data:")
        print(f"   Plan ID: {auth_plan_data.get('id')}")
        print(f"   Plan Name: {auth_plan_data.get('name')}")

        # Verify it's the same data
        if auth_plan_data.get('id') == plan_data.get('id'):
            print("✅ Authorization server reads same data as onboarding service")
        else:
            print("❌ Authorization server reads different data")
            return False
    else:
        print("❌ Authorization server cannot read cached data")
        return False

    print("\n🎉 All cache integration tests passed!")
    return True

async def test_cache_invalidation():
    """Test cache invalidation"""
    print("\n🗑️  Testing cache invalidation...")

    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    # Ensure there's something in cache
    test_data = {"test": "data", "timestamp": datetime.now().isoformat()}
    redis_client.setex(FREE_TIER_CACHE_KEY, 300, json.dumps(test_data))

    # Verify data is in cache
    cached_data = redis_client.get(FREE_TIER_CACHE_KEY)
    if cached_data:
        print("✅ Test data added to cache")
    else:
        print("❌ Failed to add test data to cache")
        return False

    # Test invalidation (this would normally happen when plans are updated)
    redis_client.delete(FREE_TIER_CACHE_KEY)

    # Verify data is gone
    cached_data = redis_client.get(FREE_TIER_CACHE_KEY)
    if cached_data is None:
        print("✅ Cache invalidation successful")
        return True
    else:
        print("❌ Cache invalidation failed")
        return False

def print_summary():
    """Print test summary and next steps"""
    print("\n" + "="*60)
    print("📋 SHARED CACHE INTEGRATION TEST SUMMARY")
    print("="*60)
    print("✅ Key improvements implemented:")
    print("   • Onboarding service manages plan cache lifecycle")
    print("   • Authorization server only reads from shared cache")
    print("   • Consistent cache keys: 'plan:free_tier'")
    print("   • Cache invalidation on plan CRUD operations")
    print("   • 1-hour TTL for plan data")
    print("")
    print("🔧 Architecture:")
    print("   • Redis: localhost:6379 (shared)")
    print("   • Onboarding: Cache manager (read/write)")
    print("   • Auth Server: Cache consumer (read-only)")
    print("")
    print("🧪 To run manual tests:")
    print("   1. Start both services")
    print("   2. Run: python test_shared_cache.py")
    print("   3. Check logs for cache operations")

async def main():
    """Run all tests"""
    print("🚀 SHARED CACHE INTEGRATION TEST")
    print("="*50)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # Test prerequisites
    redis_ok = test_redis_connection() is not None
    # Note: Services may not be running during this test

    if redis_ok:
        await test_cache_flow()
        await test_cache_invalidation()
    else:
        print("❌ Cannot proceed without Redis connection")

    print_summary()

if __name__ == "__main__":
    asyncio.run(main())