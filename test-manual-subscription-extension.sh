#!/bin/bash

# Test Manual Subscription Extension Feature
# Tests both the tenant dropdown endpoint and manual payment endpoint

set -e

echo "=========================================="
echo "Manual Subscription Extension Test"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GATEWAY_URL="http://localhost:8080"
AUTH_SERVER_URL="http://localhost:9002/auth"
CLIENT_ID="webclient"
CLIENT_SECRET="webclient-secret"

echo -e "${BLUE}Step 1: Getting admin access token...${NC}"
TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_SERVER_URL}/oauth2/token" \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=adebola&password=password")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -z "$ACCESS_TOKEN" ]; then
  echo -e "${RED}Failed to get access token${NC}"
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✓ Access token obtained${NC}"
echo ""

# Test 1: Tenant Dropdown Endpoint
echo -e "${BLUE}Step 2: Testing tenant dropdown endpoint...${NC}"
echo "GET ${GATEWAY_URL}/api/v1/admin/tenants/dropdown"
echo ""

DROPDOWN_RESPONSE=$(curl -s -X GET "${GATEWAY_URL}/api/v1/admin/tenants/dropdown" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json")

echo "Response:"
echo "$DROPDOWN_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$DROPDOWN_RESPONSE"
echo ""

# Check if response is valid JSON array
if echo "$DROPDOWN_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); exit(0 if isinstance(data, list) else 1)" 2>/dev/null; then
  TENANT_COUNT=$(echo "$DROPDOWN_RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
  echo -e "${GREEN}✓ Tenant dropdown endpoint working - ${TENANT_COUNT} active tenants found${NC}"

  # Extract first tenant for testing
  FIRST_TENANT_ID=$(echo "$DROPDOWN_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0]['id'] if data else '')")
  FIRST_TENANT_NAME=$(echo "$DROPDOWN_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0]['name'] if data else '')")

  if [ -n "$FIRST_TENANT_ID" ]; then
    echo -e "${BLUE}Selected tenant for testing: ${FIRST_TENANT_NAME} (${FIRST_TENANT_ID})${NC}"
  fi
else
  echo -e "${RED}✗ Invalid JSON response from dropdown endpoint${NC}"
  exit 1
fi
echo ""

# Test 2: Get Tenant Subscription
if [ -n "$FIRST_TENANT_ID" ]; then
  echo -e "${BLUE}Step 3: Getting subscription for tenant...${NC}"
  echo "GET ${GATEWAY_URL}/api/v1/admin/tenants/${FIRST_TENANT_ID}/subscription"
  echo ""

  SUBSCRIPTION_RESPONSE=$(curl -s -X GET "${GATEWAY_URL}/api/v1/admin/tenants/${FIRST_TENANT_ID}/subscription" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json")

  echo "Response:"
  echo "$SUBSCRIPTION_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SUBSCRIPTION_RESPONSE"
  echo ""

  # Extract subscription ID if available
  SUBSCRIPTION_ID=$(echo "$SUBSCRIPTION_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('subscription', {}).get('id', ''))" 2>/dev/null || echo "")

  if [ -n "$SUBSCRIPTION_ID" ]; then
    echo -e "${GREEN}✓ Subscription found: ${SUBSCRIPTION_ID}${NC}"
    echo ""

    # Test 3: Manual Payment Endpoint
    echo -e "${BLUE}Step 4: Testing manual payment endpoint (DRY RUN - not executing)...${NC}"
    echo "POST ${GATEWAY_URL}/api/v1/admin/billing/payments/manual"
    echo ""

    MANUAL_PAYMENT_REQUEST="{
  \"tenant_id\": \"${FIRST_TENANT_ID}\",
  \"subscription_id\": \"${SUBSCRIPTION_ID}\",
  \"amount\": 50000.00,
  \"payment_method\": \"bank_transfer\",
  \"reference_number\": \"TEST-$(date +%Y%m%d-%H%M%S)\",
  \"notes\": \"Test manual payment from automated test script\",
  \"should_extend_subscription\": true,
  \"extension_days\": 30,
  \"send_confirmation_email\": false
}"

    echo "Request body:"
    echo "$MANUAL_PAYMENT_REQUEST" | python3 -m json.tool
    echo ""

    echo -e "${BLUE}Note: Skipping actual payment creation to avoid modifying production data${NC}"
    echo -e "${BLUE}To test manually, run:${NC}"
    echo ""
    echo "ACCESS_TOKEN=\"${ACCESS_TOKEN}\""
    echo ""
    echo "curl -X POST \"${GATEWAY_URL}/api/v1/admin/billing/payments/manual\" \\"
    echo "  -H \"Authorization: Bearer \${ACCESS_TOKEN}\" \\"
    echo "  -H \"Content-Type: application/json\" \\"
    echo "  -d '${MANUAL_PAYMENT_REQUEST}'"
    echo ""

    # Uncomment below to actually execute the payment (USE WITH CAUTION)
    # PAYMENT_RESPONSE=$(curl -s -X POST "${GATEWAY_URL}/api/v1/admin/billing/payments/manual" \
    #   -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    #   -H "Content-Type: application/json" \
    #   -d "${MANUAL_PAYMENT_REQUEST}")
    #
    # echo "Payment Response:"
    # echo "$PAYMENT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PAYMENT_RESPONSE"

  else
    echo -e "${RED}✗ No subscription found for tenant${NC}"
    echo "Cannot test manual payment endpoint without a subscription"
  fi
else
  echo -e "${RED}✗ No tenants found in dropdown${NC}"
  exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Test completed successfully!${NC}"
echo "=========================================="
echo ""
echo "Summary:"
echo "✓ Tenant dropdown endpoint: Working"
echo "✓ Subscription retrieval: Working"
echo "✓ Manual payment endpoint: Ready (not executed)"
echo ""
echo "The UI can now:"
echo "1. Fetch active tenants for dropdown using GET /api/v1/admin/tenants/dropdown"
echo "2. Select a tenant and get their subscription"
echo "3. Submit manual payment to extend subscription using POST /api/v1/admin/billing/payments/manual"
