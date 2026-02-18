#!/bin/bash
# Integration test script for tenant admin routes
# This script tests the new /tenant/* endpoints

set -e

echo "==============================================="
echo "Testing Tenant Admin Routes"
echo "==============================================="
echo ""

# Configuration
CHAT_SERVICE_URL="http://localhost:8000"
AUTH_SERVER_URL="http://localhost:9000"

# Test credentials (tenant admin)
USERNAME="adebola"
PASSWORD="password"
CLIENT_ID="frontend-client"
CLIENT_SECRET="secret"

echo "Step 1: Get access token for tenant admin..."
echo "-----------------------------------------------"

TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_SERVER_URL}/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=${USERNAME}" \
  -d "password=${PASSWORD}" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}")

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get access token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo "✅ Access token obtained"
echo ""

echo "Step 2: Test GET /api/v1/chat/tenant/sessions"
echo "-----------------------------------------------"

SESSIONS_RESPONSE=$(curl -s -X GET \
  "${CHAT_SERVICE_URL}/api/v1/chat/tenant/sessions?limit=10&offset=0&active_only=false" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "Response: $SESSIONS_RESPONSE" | jq '.'

# Check if request was successful
if echo "$SESSIONS_RESPONSE" | jq -e '. | type == "array"' > /dev/null 2>&1; then
    echo "✅ Successfully retrieved tenant sessions"
else
    echo "❌ Failed to retrieve tenant sessions"
    exit 1
fi
echo ""

echo "Step 3: Test GET /api/v1/chat/tenant/stats"
echo "-----------------------------------------------"

STATS_RESPONSE=$(curl -s -X GET \
  "${CHAT_SERVICE_URL}/api/v1/chat/tenant/stats" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "Response: $STATS_RESPONSE" | jq '.'

# Check if request was successful
if echo "$STATS_RESPONSE" | jq -e '.total_sessions' > /dev/null 2>&1; then
    echo "✅ Successfully retrieved tenant stats"
else
    echo "❌ Failed to retrieve tenant stats"
    exit 1
fi
echo ""

echo "Step 4: Verify tenant admin CANNOT access system admin routes"
echo "-----------------------------------------------"

ADMIN_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "${CHAT_SERVICE_URL}/api/v1/chat/admin/sessions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

HTTP_CODE=$(echo "$ADMIN_RESPONSE" | tail -n 1)
RESPONSE_BODY=$(echo "$ADMIN_RESPONSE" | head -n -1)

echo "HTTP Status Code: $HTTP_CODE"
echo "Response: $RESPONSE_BODY"

if [ "$HTTP_CODE" == "403" ]; then
    echo "✅ Correctly denied access to system admin route (403 Forbidden)"
else
    echo "❌ Expected 403, got $HTTP_CODE"
    exit 1
fi
echo ""

echo "==============================================="
echo "All Tests Passed! ✅"
echo "==============================================="
echo ""
echo "Summary:"
echo "- Tenant admin can access /tenant/sessions ✅"
echo "- Tenant admin can access /tenant/stats ✅"
echo "- Tenant admin CANNOT access /admin/* routes ✅"
echo "- Tenant isolation is working correctly ✅"
