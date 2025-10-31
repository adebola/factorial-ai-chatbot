#!/usr/bin/env python3
"""
Test script to verify that the shared Redis auth cache works across all services.
This script simulates token validation in different services and verifies cache sharing.
"""
import asyncio
import os
import sys
import time
import json
from datetime import datetime, timedelta

# Add service paths to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "onboarding-service"))
sys.path.append(os.path.join(os.path.dirname(__file__), "chat-service"))
sys.path.append(os.path.join(os.path.dirname(__file__), "communications-service"))
sys.path.append(os.path.join(os.path.dirname(__file__), "workflow-service"))

# Set environment variables if not already set
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth")


async def test_shared_cache():
    """Test that auth cache is shared across all services"""

    print("=" * 80)
    print("TESTING SHARED REDIS AUTH CACHE ACROSS MICROSERVICES")
    print("=" * 80)
    print()

    # Import cache modules from each service
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "onboarding-service"))
        from app.services.redis_auth_cache import RedisTokenCache as OnboardingCache

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "chat-service"))
        from app.services.redis_auth_cache import RedisTokenCache as ChatCache

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "communications-service"))
        from app.services.redis_auth_cache import RedisTokenCache as CommsCache

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "workflow-service"))
        from app.services.redis_auth_cache import RedisTokenCache as WorkflowCache

        print("✅ Successfully imported auth cache modules from all services")
    except ImportError as e:
        print(f"❌ Failed to import cache modules: {e}")
        print("   Make sure all services have the redis_auth_cache.py file")
        return False

    # Create cache instances for each service
    # They should all connect to the same Redis instance
    onboarding_cache = OnboardingCache()
    chat_cache = ChatCache()
    comms_cache = CommsCache()
    workflow_cache = WorkflowCache()

    print("✅ Created cache instances for all services")
    print()

    # Create a mock token and token info
    mock_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test_token_" + str(int(time.time()))
    mock_token_info = {
        "active": True,
        "sub": "test_user_123",
        "user_id": "test_user_123",
        "tenant_id": "test_tenant_456",
        "email": "test@example.com",
        "full_name": "Test User",
        "authorities": ["ROLE_USER"],
        "exp": int((datetime.now() + timedelta(minutes=30)).timestamp()),
        "iat": int(datetime.now().timestamp()),
        "iss": "http://localhost:9002/auth"
    }

    print("📝 Test Token Info:")
    print(json.dumps(mock_token_info, indent=2))
    print()

    # Test 1: Clear all caches first
    print("🧹 Clearing all existing cache entries...")
    await onboarding_cache.clear_all()
    print("   Cache cleared")
    print()

    # Test 2: Store token in onboarding service cache
    print("📥 Test 1: Storing token in ONBOARDING service cache...")
    success = await onboarding_cache.set(mock_token, mock_token_info)
    if success:
        print("   ✅ Token cached successfully in onboarding service")
    else:
        print("   ❌ Failed to cache token in onboarding service")
        return False
    print()

    # Test 3: Retrieve token from chat service cache
    print("📤 Test 2: Retrieving token from CHAT service cache...")
    cached_info = await chat_cache.get(mock_token)
    if cached_info:
        print("   ✅ Token found in chat service cache!")
        print(f"   User ID: {cached_info.get('user_id')}")
        print(f"   Tenant ID: {cached_info.get('tenant_id')}")
    else:
        print("   ❌ Token NOT found in chat service cache")
        return False
    print()

    # Test 4: Retrieve token from communications service cache
    print("📤 Test 3: Retrieving token from COMMUNICATIONS service cache...")
    cached_info = await comms_cache.get(mock_token)
    if cached_info:
        print("   ✅ Token found in communications service cache!")
        print(f"   Email: {cached_info.get('email')}")
    else:
        print("   ❌ Token NOT found in communications service cache")
        return False
    print()

    # Test 5: Retrieve token from workflow service cache
    print("📤 Test 4: Retrieving token from WORKFLOW service cache...")
    cached_info = await workflow_cache.get(mock_token)
    if cached_info:
        print("   ✅ Token found in workflow service cache!")
        print(f"   Authorities: {cached_info.get('authorities')}")
    else:
        print("   ❌ Token NOT found in workflow service cache")
        return False
    print()

    # Test 6: Get metrics from each service (they should all show the same cache)
    print("📊 Cache Metrics from Each Service:")
    print("-" * 40)

    for service_name, cache in [
        ("Onboarding", onboarding_cache),
        ("Chat", chat_cache),
        ("Communications", comms_cache),
        ("Workflow", workflow_cache)
    ]:
        metrics = await cache.get_metrics()
        print(f"   {service_name:15} - Hits: {metrics['hits']}, Misses: {metrics['misses']}, "
              f"Cache Size: {metrics['cache_size']}")
    print()

    # Test 7: Invalidate token from workflow service
    print("🗑️  Test 5: Invalidating token from WORKFLOW service...")
    invalidated = await workflow_cache.invalidate(mock_token)
    if invalidated:
        print("   ✅ Token invalidated from workflow service")
    else:
        print("   ⚠️  Token was not in cache (already invalidated?)")
    print()

    # Test 8: Verify token is gone from all services
    print("🔍 Test 6: Verifying token is removed from all services...")
    all_removed = True
    for service_name, cache in [
        ("Onboarding", onboarding_cache),
        ("Chat", chat_cache),
        ("Communications", comms_cache),
        ("Workflow", workflow_cache)
    ]:
        cached_info = await cache.get(mock_token)
        if cached_info:
            print(f"   ❌ Token still found in {service_name} cache")
            all_removed = False
        else:
            print(f"   ✅ Token removed from {service_name} cache")
    print()

    if not all_removed:
        return False

    # Test 9: Test TTL expiration
    print("⏱️  Test 7: Testing TTL-based expiration...")

    # Create a token that expires in 2 seconds
    short_lived_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.short_lived_" + str(int(time.time()))
    short_lived_info = mock_token_info.copy()
    short_lived_info["exp"] = int((datetime.now() + timedelta(seconds=2)).timestamp())

    # Store in onboarding cache
    await onboarding_cache.set(short_lived_token, short_lived_info)
    print("   Token stored with 2-second expiration")

    # Verify it's accessible immediately
    cached = await chat_cache.get(short_lived_token)
    if cached:
        print("   ✅ Token accessible immediately from chat service")
    else:
        print("   ❌ Token not accessible immediately")
        return False

    # Wait for expiration
    print("   Waiting 3 seconds for token to expire...")
    await asyncio.sleep(3)

    # Try to retrieve expired token
    cached = await comms_cache.get(short_lived_token)
    if cached:
        print("   ❌ Expired token still returned from cache")
        return False
    else:
        print("   ✅ Expired token correctly removed from cache")
    print()

    # Final health check
    print("🏥 Test 8: Health check for all cache instances...")
    all_healthy = True
    for service_name, cache in [
        ("Onboarding", onboarding_cache),
        ("Chat", chat_cache),
        ("Communications", comms_cache),
        ("Workflow", workflow_cache)
    ]:
        healthy = await cache.health_check()
        status = "✅ Healthy" if healthy else "❌ Unhealthy"
        print(f"   {service_name:15} - {status}")
        all_healthy = all_healthy and healthy
    print()

    return all_healthy


async def main():
    """Main test runner"""
    try:
        # Check if Redis is available
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        print("✅ Redis connection successful")
        print()
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Make sure Redis is running on localhost:6379")
        return 1

    # Run the tests
    success = await test_shared_cache()

    print("=" * 80)
    if success:
        print("✅ ALL TESTS PASSED - Shared auth cache is working correctly!")
        print("   Tokens cached in any service are accessible from all services.")
        print("   Token expiration and invalidation work across all services.")
    else:
        print("❌ SOME TESTS FAILED - Check the output above for details")
    print("=" * 80)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)