"""
Test Redis caching performance for AI Agent tools

Usage:
    python scripts/test_caching.py

Requires:
    - Valid JWT token (get from /token endpoint)
    - Redis configured on Railway
"""

import time
import requests
import json
import os
import sys

BASE_URL = os.getenv("API_URL", "https://mortgage-crm-production-7a9a.up.railway.app")
TOKEN = os.getenv("TOKEN", "")


def get_token():
    """Get a fresh token"""
    response = requests.post(
        f"{BASE_URL}/token",
        data={
            "username": "admin@perenniaai.com",
            "password": "demo123"
        }
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


def chat(message: str, token: str) -> dict:
    """Send chat request"""
    response = requests.post(
        f"{BASE_URL}/api/v1/ai/langgraph-chat",
        json={"message": message},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        timeout=120
    )
    return response.json()


def get_cache_status(token: str) -> dict:
    """Get cache status"""
    response = requests.get(
        f"{BASE_URL}/api/v1/cache/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    return response.json()


def test_cache_performance():
    """Test cache hit/miss performance"""

    # Get token
    token = TOKEN or get_token()
    if not token:
        print("Failed to get token. Set TOKEN env var or check credentials.")
        sys.exit(1)

    query = "Show me my pipeline"

    print("Testing cache performance...\n")
    print("=" * 60)

    # Check initial cache status
    print("\nCache Status (before tests):")
    try:
        cache_stats = get_cache_status(token)
        print(f"   Connected: {cache_stats.get('cache', {}).get('connected', False)}")
        print(f"   Keys: {cache_stats.get('cache', {}).get('keys', 0)}")
    except Exception as e:
        print(f"   Could not get cache status: {e}")

    # Test 1: Cold cache (first query)
    print("\n1. COLD CACHE (first query - should hit database)")
    start = time.time()
    result1 = chat(query, token)
    cold_time = time.time() - start

    print(f"   Response time: {cold_time:.2f}s")
    if "error" in result1:
        print(f"   Error: {result1.get('error')}")
    else:
        tools = result1.get('metadata', {}).get('tools_used', [])
        print(f"   Tools used: {tools}")

    # Wait a moment
    time.sleep(2)

    # Test 2: Warm cache (second query - same question)
    print("\n2. WARM CACHE (second query - should hit cache)")
    start = time.time()
    result2 = chat(query, token)
    warm_time = time.time() - start

    print(f"   Response time: {warm_time:.2f}s")
    if "error" not in result2:
        tools = result2.get('metadata', {}).get('tools_used', [])
        print(f"   Tools used: {tools}")

    # Test 3: Warm cache again
    print("\n3. WARM CACHE (third query - should hit cache)")
    start = time.time()
    result3 = chat(query, token)
    warm_time2 = time.time() - start

    print(f"   Response time: {warm_time2:.2f}s")

    # Calculate speedup
    avg_warm = (warm_time + warm_time2) / 2
    speedup = cold_time / avg_warm if avg_warm > 0 else 1

    print("\n" + "=" * 60)
    print("\nRESULTS:")
    print(f"   Cold cache:     {cold_time:.2f}s")
    print(f"   Warm cache #1:  {warm_time:.2f}s")
    print(f"   Warm cache #2:  {warm_time2:.2f}s")
    print(f"   Avg warm:       {avg_warm:.2f}s")
    print(f"   Speedup:        {speedup:.1f}x")

    if cold_time > avg_warm:
        improvement = ((cold_time - avg_warm) / cold_time * 100)
        print(f"   Improvement:    {improvement:.0f}%")

    # Check cache status after tests
    print("\nCache Status (after tests):")
    try:
        cache_stats = get_cache_status(token)
        print(f"   Connected: {cache_stats.get('cache', {}).get('connected', False)}")
        print(f"   Keys: {cache_stats.get('cache', {}).get('keys', 0)}")
        print(f"   Memory: {cache_stats.get('cache', {}).get('memory_used', 'N/A')}")
    except Exception as e:
        print(f"   Could not get cache status: {e}")

    print("\n" + "=" * 60)

    if speedup > 1.5:
        print("\nCACHE WORKING! Repeat queries are faster")
        return True
    elif speedup > 1.1:
        print("\nCache may be working - slight improvement detected")
        return True
    else:
        print("\nCache might not be working - times are similar")
        print("   - Check if REDIS_URL is set in Railway")
        print("   - Check /health/cache endpoint")
        return False


def test_different_queries():
    """Test that different queries don't share cache"""

    token = TOKEN or get_token()
    if not token:
        print("Failed to get token")
        return

    print("\n" + "=" * 60)
    print("Testing different queries...\n")

    queries = [
        "Show me my pipeline",
        "What are my tasks for today?",
        "Show me my priorities"
    ]

    for query in queries:
        print(f"Query: '{query[:40]}...'")
        start = time.time()
        result = chat(query, token)
        elapsed = time.time() - start
        print(f"   Time: {elapsed:.2f}s")
        time.sleep(1)

    print("\nNote: First call for each unique query should be slower (cache miss)")


if __name__ == "__main__":
    test_cache_performance()
    test_different_queries()
