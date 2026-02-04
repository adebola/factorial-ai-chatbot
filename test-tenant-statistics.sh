#!/bin/bash

# Test script for tenant statistics enhancement (Simplified Token Forwarding)
# This script tests the complete flow:
# 1. Get system admin user token
# 2. Test onboarding stats endpoint
# 3. Test chat stats endpoint
# 4. Test tenant statistics endpoint (which forwards the same token)

set -e

echo "============================================"
echo "Testing Tenant Statistics Enhancement"
echo "Simple Token Forwarding Approach"
echo "============================================"
echo ""

# Configuration
AUTH_SERVER="http://localhost:9002/auth"
CHAT_SERVICE="http://localhost:8000"
ONBOARDING_SERVICE="http://localhost:8001"
TENANT_ID="5190e7b2-04c1-477d-8dca-84462baf7bd3"

# System admin credentials (from CLAUDE.md test credentials)
ADMIN_USERNAME="adebola"
ADMIN_PASSWORD="password"

echo "Step 1: Get system admin token (password grant)..."
echo "-------------------------------------------"

# Note: This uses a system admin user with ROLE_SYSTEM_ADMIN
# The exact OAuth2 client and flow may vary based on your setup
# Adjust client_id/client_secret as needed for your environment

TOKEN_RESPONSE=$(curl -s -X POST "$AUTH_SERVER/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=$ADMIN_USERNAME&password=$ADMIN_PASSWORD&client_id=webclient&client_secret=secret123" 2>&1)

echo "Token Response:"
echo "$TOKEN_RESPONSE" | jq . 2>/dev/null || echo "$TOKEN_RESPONSE"

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to obtain access token"
    echo ""
    echo "Note: You may need to adjust the OAuth2 client configuration."
    echo "The test credentials are: username=$ADMIN_USERNAME, password=$ADMIN_PASSWORD"
    echo ""
    echo "Alternative: Get a token manually from your admin application and run:"
    echo "  export ACCESS_TOKEN='your-token-here'"
    echo "  ./test-tenant-statistics.sh"

    # Check if ACCESS_TOKEN is set in environment
    if [ -n "$ACCESS_TOKEN" ]; then
        echo ""
        echo "✓ Using ACCESS_TOKEN from environment variable"
    else
        exit 1
    fi
else
    echo "✓ Access token obtained successfully"
    echo "Token: ${ACCESS_TOKEN:0:50}..."
fi

echo ""

echo "Step 2: Test Onboarding Service Admin Stats..."
echo "-------------------------------------------"

ONBOARDING_STATS=$(curl -s -X GET "$ONBOARDING_SERVICE/api/v1/admin/stats?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json")

echo "Onboarding Stats Response:"
echo "$ONBOARDING_STATS" | jq .

NUM_DOCUMENTS=$(echo "$ONBOARDING_STATS" | jq -r '.num_documents')
NUM_WEBSITES=$(echo "$ONBOARDING_STATS" | jq -r '.num_websites')
STORAGE_USED_MB=$(echo "$ONBOARDING_STATS" | jq -r '.storage_used_mb')

echo "✓ Onboarding stats retrieved:"
echo "  - Documents: $NUM_DOCUMENTS"
echo "  - Websites: $NUM_WEBSITES"
echo "  - Storage: $STORAGE_USED_MB MB"
echo ""

echo "Step 3: Test Chat Service Admin Stats..."
echo "-------------------------------------------"

CHAT_STATS=$(curl -s -X GET "$CHAT_SERVICE/api/v1/admin/stats?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json")

echo "Chat Stats Response:"
echo "$CHAT_STATS" | jq .

TOTAL_SESSIONS=$(echo "$CHAT_STATS" | jq -r '.total_sessions')
TOTAL_MESSAGES=$(echo "$CHAT_STATS" | jq -r '.total_messages')

echo "✓ Chat stats retrieved:"
echo "  - Sessions: $TOTAL_SESSIONS"
echo "  - Messages: $TOTAL_MESSAGES"
echo ""

echo "Step 4: Test Tenant Statistics Endpoint (Authorization Server)..."
echo "-------------------------------------------"
echo "This endpoint forwards the SAME token to chat and onboarding services"
echo ""

TENANT_STATS=$(curl -s -X GET "$AUTH_SERVER/api/v1/admin/tenants/$TENANT_ID/statistics" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json")

echo "Tenant Statistics Response:"
echo "$TENANT_STATS" | jq .

echo ""
echo "============================================"
echo "Verification"
echo "============================================"

# Verify all fields are present
FIELDS=("total_users" "active_users" "total_chats" "total_messages" "num_documents" "num_websites" "storage_used_mb" "last_activity")

ALL_PRESENT=true
for FIELD in "${FIELDS[@]}"; do
    VALUE=$(echo "$TENANT_STATS" | jq -r ".$FIELD")
    if [ "$VALUE" == "null" ]; then
        echo "❌ Field missing: $FIELD"
        ALL_PRESENT=false
    else
        echo "✓ $FIELD: $VALUE"
    fi
done

echo ""
if [ "$ALL_PRESENT" = true ]; then
    echo "✓ All fields present in tenant statistics"
    echo "✓ TEST PASSED"
    echo ""
    echo "Key Point: The authorization server simply forwarded the"
    echo "same Bearer token to chat and onboarding services!"
else
    echo "❌ Some fields are missing"
    echo "❌ TEST FAILED"
    exit 1
fi

echo ""
echo "============================================"
echo "Graceful Degradation Test"
echo "============================================"
echo "To test graceful degradation:"
echo "1. Stop chat service: Statistics should return total_chats=0, total_messages=0"
echo "2. Stop onboarding service: Statistics should return num_documents=0, num_websites=0, storage_used_mb=0"
echo "============================================"
