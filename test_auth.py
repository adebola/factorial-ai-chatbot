#!/usr/bin/env python3
"""Test authentication across services"""
import requests
import json
import sys

# First, we need to find a valid client_id and client_secret
# Let's get a token using basic auth with username/password

def get_token():
    """Get token from authorization server"""

    # Using password grant type
    token_url = "http://localhost:9002/auth/oauth2/token"

    # Try with webclient (found in database)
    data = {
        "grant_type": "password",
        "username": "adebola",
        "password": "password",
        "scope": "openid profile email"
    }

    # Basic auth with client credentials
    auth = ("webclient", "webclient-secret")

    response = requests.post(
        token_url,
        data=data,
        auth=auth,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    print(f"Token request status: {response.status_code}")
    print(f"Token response: {response.text}")

    if response.status_code == 200:
        return response.json().get("access_token")
    return None


def test_communications_service(token):
    """Test the communications service with token"""

    # Test the email templates endpoint
    url = "http://localhost:8003/api/v1/email/templates"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    print(f"\nCommunications service test:")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500] if response.text else 'No content'}")

    return response.status_code == 200


def main():
    print("Testing authentication flow...")

    # Get token
    token = get_token()

    if not token:
        print("\nFailed to get token.")
        return 1

    print(f"\nGot token: {token[:50]}...")

    # Test communications service
    if test_communications_service(token):
        print("\n✅ Authentication working!")
        return 0
    else:
        print("\n❌ Authentication failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())