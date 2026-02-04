#!/bin/bash

# Test script to verify the system admin 401 authentication fix
# This script tests that super admin users can successfully access admin endpoints

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== System Admin Authentication Fix Test ===${NC}"
echo ""

# Configuration
AUTH_SERVER="http://localhost:9002/auth"
CLIENT_ID="superadmin-client"
REDIRECT_URI="http://localhost:4201/callback"

# Test credentials (from CLAUDE.md)
USERNAME="admin"
PASSWORD="password"

echo -e "${YELLOW}Step 1: Get authorization code${NC}"
echo "Opening browser for login..."
echo "Please login with:"
echo "  Username: ${USERNAME}"
echo "  Password: ${PASSWORD}"
echo ""

# Generate a random state
STATE=$(openssl rand -hex 16)

# Generate PKCE verifier and challenge
CODE_VERIFIER=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-43)
CODE_CHALLENGE=$(echo -n "$CODE_VERIFIER" | openssl dgst -binary -sha256 | openssl base64 | tr -d "=+/" | cut -c1-43)

# Authorization URL
AUTH_URL="${AUTH_SERVER}/oauth2/authorize?response_type=code&client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&scope=openid%20profile%20read%20write%20admin%20system-admin&state=${STATE}&code_challenge=${CODE_CHALLENGE}&code_challenge_method=S256"

echo "Authorization URL:"
echo "$AUTH_URL"
echo ""
echo -e "${YELLOW}Please manually visit the URL above, login, and paste the authorization code from the redirect URL:${NC}"
read -p "Authorization code: " AUTH_CODE

if [ -z "$AUTH_CODE" ]; then
    echo -e "${RED}Error: No authorization code provided${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Exchange authorization code for access token${NC}"

TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_SERVER}/oauth2/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=authorization_code" \
    -d "code=${AUTH_CODE}" \
    -d "redirect_uri=${REDIRECT_URI}" \
    -d "client_id=${CLIENT_ID}" \
    -d "code_verifier=${CODE_VERIFIER}")

echo "Token response:"
echo "$TOKEN_RESPONSE" | jq '.'

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" == "null" ]; then
    echo -e "${RED}Error: Failed to get access token${NC}"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Successfully obtained access token${NC}"
echo ""

echo -e "${YELLOW}Step 3: Decode JWT token to verify claims${NC}"
# Decode JWT payload (second part)
PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '.')

echo "JWT Claims:"
echo "$PAYLOAD" | jq '.'
echo ""

# Check for authorities claim
AUTHORITIES=$(echo "$PAYLOAD" | jq -r '.authorities[]' 2>/dev/null)
echo "Authorities found in token:"
echo "$AUTHORITIES"
echo ""

if echo "$AUTHORITIES" | grep -q "ROLE_SYSTEM_ADMIN"; then
    echo -e "${GREEN}✓ Token contains ROLE_SYSTEM_ADMIN authority${NC}"
else
    echo -e "${RED}✗ Token does NOT contain ROLE_SYSTEM_ADMIN authority${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 4: Test admin endpoints (This is the critical test!)${NC}"
echo ""

# Test 1: Get all tenants (requires ROLE_SYSTEM_ADMIN)
echo "Test 1: GET /api/v1/admin/tenants"
TENANTS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    "${AUTH_SERVER}/api/v1/admin/tenants")

HTTP_STATUS=$(echo "$TENANTS_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$TENANTS_RESPONSE" | sed '/HTTP_STATUS:/d')

echo "Status Code: $HTTP_STATUS"
echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo ""

if [ "$HTTP_STATUS" == "200" ]; then
    echo -e "${GREEN}✓ Test 1 PASSED: Admin endpoint returned 200 OK${NC}"
else
    echo -e "${RED}✗ Test 1 FAILED: Expected 200, got $HTTP_STATUS${NC}"
    echo -e "${RED}This indicates the JWT converter is NOT extracting authorities correctly${NC}"
    exit 1
fi

echo ""
# Test 2: Get all users (requires ROLE_SYSTEM_ADMIN)
echo "Test 2: GET /api/v1/admin/users"
USERS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    "${AUTH_SERVER}/api/v1/admin/users")

HTTP_STATUS=$(echo "$USERS_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$USERS_RESPONSE" | sed '/HTTP_STATUS:/d')

echo "Status Code: $HTTP_STATUS"
echo "Response:"
echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
echo ""

if [ "$HTTP_STATUS" == "200" ]; then
    echo -e "${GREEN}✓ Test 2 PASSED: Admin endpoint returned 200 OK${NC}"
else
    echo -e "${RED}✗ Test 2 FAILED: Expected 200, got $HTTP_STATUS${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Summary:"
echo "- JWT token contains 'authorities' claim with ROLE_SYSTEM_ADMIN ✓"
echo "- Admin endpoints return 200 OK (not 401) ✓"
echo "- JwtAuthenticationConverter correctly extracts authorities ✓"
echo ""
echo -e "${GREEN}The 401 authentication issue has been FIXED!${NC}"
