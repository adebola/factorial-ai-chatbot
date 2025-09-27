#!/usr/bin/env python3
"""Test communications service authentication"""
import requests
import sys

# Step 1: Get a client credentials token (no user context)
def get_client_token():
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

# Step 2: Test introspection directly
def test_introspection(token):
    response = requests.post(
        "http://localhost:9002/auth/oauth2/introspect",
        auth=("webclient", "webclient-secret"),
        data={
            "token": token,
            "token_type_hint": "access_token"
        }
    )
    print("Token introspection response:")
    print(response.json())
    return response.json()

# Step 3: Test communications service
def test_comms_api(token):
    response = requests.get(
        "http://localhost:8003/api/v1/email/templates",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )
    print(f"\nCommunications API response: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: {response.text}")
    return response.status_code == 200

def main():
    print("Testing communications service authentication...")

    # Get token
    token = get_client_token()
    if not token:
        return 1

    print(f"Got token: {token[:50]}...")

    # Test introspection
    introspection_result = test_introspection(token)

    # Check if token has required claims
    if not introspection_result.get("active"):
        print("Token is not active!")
        return 1

    # Note: Client credentials tokens don't have tenant_id or user_id
    # The communications service needs these claims
    print("\nNote: Client credentials tokens lack tenant_id and user_id")
    print("Communications service will reject this token.")

    # Test anyway to confirm the error
    success = test_comms_api(token)

    if not success:
        print("\nAs expected, authentication failed due to missing user context.")
        print("To fix this, we need to either:")
        print("1. Use authorization code flow with a real user")
        print("2. Update the auth server to support password grant")
        print("3. Make communications service accept client-only tokens for some operations")

    return 0

if __name__ == "__main__":
    sys.exit(main())