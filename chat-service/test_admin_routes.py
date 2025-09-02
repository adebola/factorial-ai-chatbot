#!/usr/bin/env python3
"""
Test script for chat admin routes
This script demonstrates how to use the new admin endpoints
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"  # Direct to chat service for testing
# BASE_URL = "http://localhost:8080"  # Via gateway (uncomment if testing through gateway)

# Replace with a valid tenant API key from your database
TEST_API_KEY = "your-tenant-api-key-here"

def test_admin_routes():
    """Test all admin chat routes"""
    headers = {"Content-Type": "application/json"}
    
    print("🧪 Testing Chat Admin Routes")
    print("=" * 50)
    
    # Test 1: Get chat statistics
    print("\n1️⃣ Testing chat statistics...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/chat/admin/stats",
            params={"api_key": TEST_API_KEY},
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            stats = response.json()
            print(f"📊 Stats: {json.dumps(stats, indent=2)}")
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    
    # Test 2: List chat sessions
    print("\n2️⃣ Testing session listing...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/chat/admin/sessions",
            params={
                "api_key": TEST_API_KEY,
                "limit": 10,
                "offset": 0
            },
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            sessions = response.json()
            print(f"📋 Found {len(sessions)} sessions")
            for session in sessions[:3]:  # Show first 3
                print(f"   - Session: {session['session_id']} ({session['message_count']} messages)")
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    
    # Test 3: Search messages (if there are any)
    print("\n3️⃣ Testing message search...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/chat/admin/messages/search",
            params={
                "api_key": TEST_API_KEY,
                "query": "hello",
                "limit": 5
            },
            headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            messages = response.json()
            print(f"🔍 Found {len(messages)} messages with 'hello'")
            for msg in messages:
                print(f"   - {msg['message_type']}: {msg['content'][:50]}...")
        else:
            print(f"❌ Error: {response.text}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    
    print("\n✅ Admin routes testing completed!")
    print("\nNOTE: To get real data, you need:")
    print("1. Replace TEST_API_KEY with a valid tenant API key")
    print("2. Ensure the chat service is running on the configured port")
    print("3. Have some chat sessions and messages in the database")

if __name__ == "__main__":
    test_admin_routes()