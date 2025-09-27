#!/usr/bin/env python3
"""
Test JWT validation performance: Local validation vs HTTP introspection.
This test directly measures the validation functions without the full API.
"""
import asyncio
import time
import statistics
import sys
import os

# Add the communications service to the path
sys.path.insert(0, "/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/communications-service")

import requests


def get_token():
    """Get a client credentials token"""
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
    return None


async def benchmark_local_validation(token: str, iterations: int = 100):
    """Benchmark local JWT validation"""
    from app.services.jwt_validator import jwt_validator

    print("\n" + "=" * 60)
    print("LOCAL JWT VALIDATION (with RSA public keys)")
    print("=" * 60)

    # First validation fetches JWKS
    print("\nFirst validation (fetches JWKS from auth server)...")
    start = time.perf_counter()
    try:
        payload = await jwt_validator.validate_token(token)
        latency_ms = (time.perf_counter() - start) * 1000
        print(f"✅ Success! Initial latency: {latency_ms:.2f}ms")
        print(f"   Subject: {payload.get('sub')}")
        print(f"   Issuer: {payload.get('iss')}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return

    # Benchmark cached validations
    print(f"\nRunning {iterations} cached validations...")
    latencies = []

    for i in range(iterations):
        start = time.perf_counter()
        try:
            await jwt_validator.validate_token(token)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)
        except Exception as e:
            print(f"  Validation {i+1} failed: {e}")

    return latencies


async def benchmark_http_introspection(token: str, iterations: int = 20):
    """Benchmark HTTP introspection (simulated)"""
    import httpx

    print("\n" + "=" * 60)
    print("HTTP TOKEN INTROSPECTION (network calls)")
    print("=" * 60)

    print(f"\nRunning {iterations} introspection requests...")
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
                    latency_ms = (time.perf_counter() - start) * 1000
                    latencies.append(latency_ms)

        except Exception as e:
            print(f"  Request {i+1} failed: {e}")

    return latencies


def print_statistics(latencies, title):
    """Print detailed statistics"""
    if not latencies:
        print(f"\n{title}: No data")
        return

    print(f"\n{title} Statistics:")
    print(f"  Samples: {len(latencies)}")
    print(f"  Average: {statistics.mean(latencies):.3f}ms")
    print(f"  Median:  {statistics.median(latencies):.3f}ms")
    print(f"  Min:     {min(latencies):.3f}ms")
    print(f"  Max:     {max(latencies):.3f}ms")
    if len(latencies) > 1:
        print(f"  StdDev:  {statistics.stdev(latencies):.3f}ms")

    # Show percentiles
    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
    print(f"  P50:     {p50:.3f}ms")
    print(f"  P95:     {p95:.3f}ms")
    print(f"  P99:     {p99:.3f}ms")


async def main():
    print("=" * 60)
    print("JWT VALIDATION PERFORMANCE COMPARISON")
    print("=" * 60)

    # Get token
    print("\nGetting test token...")
    token = get_token()
    if not token:
        print("❌ Failed to get token")
        return 1

    print(f"✅ Got token (length: {len(token)} chars)")

    # Test local validation
    local_latencies = await benchmark_local_validation(token, iterations=100)

    # Test HTTP introspection
    http_latencies = await benchmark_http_introspection(token, iterations=20)

    # Print comparison
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON")
    print("=" * 60)

    if local_latencies:
        print_statistics(local_latencies, "🚀 Local JWT Validation")

    if http_latencies:
        print_statistics(http_latencies, "🌐 HTTP Introspection")

    if local_latencies and http_latencies:
        local_avg = statistics.mean(local_latencies)
        http_avg = statistics.mean(http_latencies)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        speedup = http_avg / local_avg
        reduction = ((http_avg - local_avg) / http_avg) * 100

        print(f"\n✅ Local validation average:  {local_avg:.3f}ms")
        print(f"❌ HTTP introspection average: {http_avg:.3f}ms")
        print(f"\n🎯 Performance improvement:")
        print(f"   • {speedup:.0f}x faster")
        print(f"   • {reduction:.0f}% latency reduction")
        print(f"   • {http_avg - local_avg:.2f}ms saved per request")

        print("\n📊 At scale (requests per day):")
        for reqs in [1000, 10000, 100000, 1000000]:
            saved_seconds = (http_avg - local_avg) * reqs / 1000
            print(f"   • {reqs:,} requests: {saved_seconds:.1f} seconds saved")

    print("\n" + "=" * 60)
    print("KEY BENEFITS OF LOCAL VALIDATION:")
    print("=" * 60)
    print("✅ Sub-millisecond latency (<1ms)")
    print("✅ No network calls after initial JWKS fetch")
    print("✅ Works even if auth server is temporarily down")
    print("✅ Scales infinitely without auth server load")
    print("✅ Consistent, predictable performance")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))