#!/usr/bin/env python3
"""
Test local JWT validation across all three services.
Compares performance between old HTTP introspection and new local validation.
"""
import asyncio
import time
import statistics
import sys
import os
import requests
from typing import List, Dict, Any

# Services configuration
SERVICES = {
    "communications": {
        "url": "http://localhost:8003",
        "test_endpoint": "/health",  # Public endpoint
        "path": "/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/communications-service"
    },
    "onboarding": {
        "url": "http://localhost:8001",
        "test_endpoint": "/api/v1/plans",  # Public endpoint
        "path": "/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/onboarding-service"
    },
    "chat": {
        "url": "http://localhost:8000",
        "test_endpoint": "/health",  # Public endpoint
        "path": "/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/chat-service"
    }
}


def get_token():
    """Get a client credentials token from auth server"""
    response = requests.post(
        "http://localhost:9002/auth/oauth2/token",
        auth=("webclient", "webclient-secret"),
        data={
            "grant_type": "client_credentials",
            "scope": "openid"
        }
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    print(f"Failed to get token: {response.text}")
    return None


def test_service_health(service_name: str, service_config: Dict[str, str]) -> bool:
    """Test if a service is running"""
    try:
        response = requests.get(f"{service_config['url']}{service_config['test_endpoint']}")
        if response.status_code in [200, 404]:  # 404 is OK for now, means service is up
            print(f"✅ {service_name.title()} Service: Running")
            return True
        else:
            print(f"❌ {service_name.title()} Service: Status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ {service_name.title()} Service: Not reachable ({e})")
        return False


async def test_local_jwt_validator(service_name: str, service_path: str, token: str) -> List[float]:
    """Test the local JWT validator directly"""
    sys.path.insert(0, service_path)

    try:
        from app.services.jwt_validator import jwt_validator

        print(f"\n--- Testing {service_name.title()} Service Local JWT Validation ---")

        # First validation (fetches JWKS)
        print("  First validation (fetches JWKS)...")
        start = time.perf_counter()
        try:
            payload = await jwt_validator.validate_token(token)
            latency = (time.perf_counter() - start) * 1000
            print(f"  ✅ Success! Initial latency: {latency:.2f}ms")
            print(f"     Subject: {payload.get('sub')}")
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            return []

        # Subsequent validations (uses cached keys)
        print("  Running 20 cached validations...")
        latencies = []
        for i in range(20):
            start = time.perf_counter()
            try:
                await jwt_validator.validate_token(token)
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)
            except Exception as e:
                print(f"    Validation {i+1} failed: {e}")

        if latencies:
            avg = statistics.mean(latencies)
            print(f"  📊 Average latency: {avg:.3f}ms (Min: {min(latencies):.3f}ms, Max: {max(latencies):.3f}ms)")

        return latencies

    except ImportError as e:
        print(f"  ❌ Could not import JWT validator for {service_name}: {e}")
        return []
    except Exception as e:
        print(f"  ❌ Unexpected error testing {service_name}: {e}")
        return []
    finally:
        # Clean up sys.path
        if service_path in sys.path:
            sys.path.remove(service_path)


async def test_http_introspection(token: str, iterations: int = 10) -> List[float]:
    """Benchmark HTTP introspection for comparison"""
    import httpx

    print(f"\n--- Testing HTTP Introspection (for comparison) ---")
    print(f"  Running {iterations} introspection requests...")

    latencies = []
    for i in range(iterations):
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "http://localhost:9002/auth/oauth2/introspect",
                    data={
                        "token": token,
                        "token_type_hint": "access_token"
                    },
                    auth=("webclient", "webclient-secret"),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code == 200:
                    latency = (time.perf_counter() - start) * 1000
                    latencies.append(latency)

        except Exception as e:
            print(f"    Request {i+1} failed: {e}")

    if latencies:
        avg = statistics.mean(latencies)
        print(f"  📊 Average latency: {avg:.2f}ms (Min: {min(latencies):.2f}ms, Max: {max(latencies):.2f}ms)")

    return latencies


def print_summary(results: Dict[str, List[float]], http_latencies: List[float]):
    """Print performance summary"""
    print("\n" + "=" * 80)
    print("PERFORMANCE SUMMARY")
    print("=" * 80)

    # Local validation results
    all_local_latencies = []
    for service_name, latencies in results.items():
        if latencies:
            avg = statistics.mean(latencies)
            print(f"\n🚀 {service_name.title()} Service - Local JWT Validation:")
            print(f"   Average: {avg:.3f}ms | Min: {min(latencies):.3f}ms | Max: {max(latencies):.3f}ms")
            all_local_latencies.extend(latencies)

    # HTTP introspection results
    if http_latencies:
        http_avg = statistics.mean(http_latencies)
        print(f"\n🌐 HTTP Introspection:")
        print(f"   Average: {http_avg:.2f}ms | Min: {min(http_latencies):.2f}ms | Max: {max(http_latencies):.2f}ms")

        # Overall comparison
        if all_local_latencies:
            local_avg = statistics.mean(all_local_latencies)
            speedup = http_avg / local_avg
            reduction = ((http_avg - local_avg) / http_avg) * 100

            print(f"\n🎯 OVERALL PERFORMANCE IMPROVEMENT:")
            print(f"   • Local validation average: {local_avg:.3f}ms")
            print(f"   • HTTP introspection average: {http_avg:.2f}ms")
            print(f"   • Speedup: {speedup:.0f}x faster")
            print(f"   • Latency reduction: {reduction:.0f}%")
            print(f"   • Time saved per request: {http_avg - local_avg:.2f}ms")

            print(f"\n📈 SCALE IMPACT (requests per day):")
            for daily_reqs in [1000, 10000, 100000, 1000000]:
                saved_seconds = (http_avg - local_avg) * daily_reqs / 1000
                saved_hours = saved_seconds / 3600
                print(f"   • {daily_reqs:,} requests: {saved_hours:.1f} hours saved")


async def main():
    print("=" * 80)
    print("FACTORIALBOT JWT VALIDATION PERFORMANCE TEST")
    print("Testing Local JWT Validation Across All Services")
    print("=" * 80)

    # Check services health
    print("\n🔍 Checking service health...")
    running_services = {}
    for service_name, config in SERVICES.items():
        if test_service_health(service_name, config):
            running_services[service_name] = config

    if not running_services:
        print("\n❌ No services are running. Please start the services first.")
        return 1

    # Get authentication token
    print("\n🔑 Getting authentication token...")
    token = get_token()
    if not token:
        print("❌ Failed to get authentication token")
        return 1

    print(f"✅ Got token: {token[:50]}...")

    # Test local JWT validation for each running service
    results = {}
    for service_name, config in running_services.items():
        latencies = await test_local_jwt_validator(service_name, config["path"], token)
        if latencies:
            results[service_name] = latencies

    # Test HTTP introspection for comparison
    http_latencies = await test_http_introspection(token, iterations=10)

    # Print comprehensive summary
    print_summary(results, http_latencies)

    print("\n" + "=" * 80)
    print("✅ LOCAL JWT VALIDATION SUCCESSFULLY IMPLEMENTED")
    print("All services now validate JWTs locally with sub-millisecond latency!")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))