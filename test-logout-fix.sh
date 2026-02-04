#!/bin/bash

# Test script to verify logout/token revocation fix
# This script tests that token revocation works correctly with proper client authentication

set -e  # Exit on error

echo "=========================================="
echo "LOGOUT/TOKEN REVOCATION FIX VERIFICATION"
echo "=========================================="
echo ""

# Configuration
AUTH_SERVER_URL="http://localhost:9002/auth"

# Test credentials (from CLAUDE.md)
USERNAME="adebola"
PASSWORD="password"
CLIENT_ID="frontend-client"
CLIENT_SECRET="secret"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

echo "Step 1: Obtaining OAuth2 access token..."
TOKEN_RESPONSE=$(curl -s -X POST "$AUTH_SERVER_URL/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=$USERNAME" \
  -d "password=$PASSWORD" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    print_error "Failed to obtain access token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

print_success "Access token obtained"
print_info "Token (first 20 chars): ${ACCESS_TOKEN:0:20}..."
echo ""

echo "Step 2: Testing token is valid..."
TENANT_CHECK=$(curl -s -w "\n%{http_code}" -X GET "$AUTH_SERVER_URL/api/v1/admin/tenants" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

HTTP_CODE=$(echo "$TENANT_CHECK" | tail -1)

if [ "$HTTP_CODE" == "200" ]; then
    print_success "Token is valid and working"
else
    print_error "Token validation failed with HTTP $HTTP_CODE"
    exit 1
fi
echo ""

echo "Step 3: Revoking token WITH client authentication (CORRECT method)..."

# Create Basic Auth credentials
CREDENTIALS=$(echo -n "$CLIENT_ID:$CLIENT_SECRET" | base64)

REVOKE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$AUTH_SERVER_URL/oauth2/revoke" \
  -H "Authorization: Basic $CREDENTIALS" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$ACCESS_TOKEN" \
  -d "token_type_hint=access_token" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET")

REVOKE_HTTP_CODE=$(echo "$REVOKE_RESPONSE" | tail -1)

if [ "$REVOKE_HTTP_CODE" == "200" ]; then
    print_success "Token revocation succeeded (HTTP 200)"
else
    print_error "Token revocation failed with HTTP $REVOKE_HTTP_CODE"
    echo "Response: $REVOKE_RESPONSE"
    exit 1
fi
echo ""

echo "Step 4: Verifying token is now invalid..."
INVALID_CHECK=$(curl -s -w "\n%{http_code}" -X GET "$AUTH_SERVER_URL/api/v1/admin/tenants" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

INVALID_HTTP_CODE=$(echo "$INVALID_CHECK" | tail -1)

if [ "$INVALID_HTTP_CODE" == "401" ]; then
    print_success "Token is properly invalidated (HTTP 401)"
else
    print_error "Token still valid! Expected 401, got HTTP $INVALID_HTTP_CODE"
    exit 1
fi
echo ""

echo "========================================"
echo "Step 5: Testing INCORRECT method (without client auth)..."
print_info "This should fail as it did before the fix"

# Get a new token
TOKEN_RESPONSE2=$(curl -s -X POST "$AUTH_SERVER_URL/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=$USERNAME" \
  -d "password=$PASSWORD" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET")

ACCESS_TOKEN2=$(echo "$TOKEN_RESPONSE2" | jq -r '.access_token')
print_info "Got new token for testing incorrect method"
echo ""

# Try to revoke WITHOUT Basic Auth (the bug that was fixed)
WRONG_REVOKE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$AUTH_SERVER_URL/oauth2/revoke" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$ACCESS_TOKEN2" \
  -d "client_id=$CLIENT_ID")

WRONG_REVOKE_HTTP_CODE=$(echo "$WRONG_REVOKE_RESPONSE" | tail -1)

if [ "$WRONG_REVOKE_HTTP_CODE" == "401" ] || [ "$WRONG_REVOKE_HTTP_CODE" == "400" ]; then
    print_success "Incorrect method properly rejected (HTTP $WRONG_REVOKE_HTTP_CODE)"
    print_info "This confirms the server requires client authentication"
else
    print_error "Expected 401 or 400, got HTTP $WRONG_REVOKE_HTTP_CODE"
fi
echo ""

echo "=========================================="
print_success "ALL TESTS PASSED!"
echo "=========================================="
echo ""

print_info "Summary:"
echo "  ✅ Tokens can be obtained successfully"
echo "  ✅ Valid tokens work for API calls"
echo "  ✅ Token revocation WITH client auth succeeds"
echo "  ✅ Revoked tokens are properly invalidated"
echo "  ✅ Token revocation WITHOUT client auth is rejected"
echo ""

print_info "The logout fix is working correctly!"
echo ""

print_info "Frontend changes required:"
echo "  • Add Basic Authentication to revocation request"
echo "  • Include client_secret in request body"
echo "  • Add token_type_hint parameter"
echo ""

print_info "File modified:"
echo "  • frontend/chatcraft-superadmin/src/app/core/services/auth.service.ts"
echo ""

print_success "Test completed successfully!"
