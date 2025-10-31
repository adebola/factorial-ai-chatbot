#!/bin/bash

# Phase 4 Testing Script
# Tests Admin Dashboard, Knowledge Gap Detection, and CSV Export

set -e  # Exit on error

BASE_URL="http://localhost:8005/api/v1"
TOKEN=""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Phase 4 Feature Testing"
echo "========================================="
echo ""

# Check if token is provided
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: ./test_phase4.sh <access-token>${NC}"
    echo ""
    echo "Get an access token first:"
    echo "  curl -X POST http://localhost:9002/auth/oauth2/token \\"
    echo "    -H 'Content-Type: application/x-www-form-urlencoded' \\"
    echo "    -d 'grant_type=password' \\"
    echo "    -d 'username=adebola' \\"
    echo "    -d 'password=password' \\"
    echo "    -d 'client_id=webclient' \\"
    echo "    -d 'client_secret=webclient-secret'"
    echo ""
    exit 1
fi

TOKEN=$1

echo -e "${YELLOW}Testing with token: ${TOKEN:0:20}...${NC}"
echo ""

# Test 1: Dashboard Overview
echo -e "${YELLOW}[1/7] Testing Dashboard Overview...${NC}"
response=$(curl -s -w "\n%{http_code}" \
    "$BASE_URL/admin/dashboard/overview?days=7" \
    -H "Authorization: Bearer $TOKEN")

status_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}✓ Dashboard overview successful${NC}"
    echo "$body" | jq -r '.metrics | "  Messages: \(.total_messages), Avg Confidence: \(.avg_confidence), Low Quality: \(.low_quality_percentage)%"'
else
    echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
    echo "$body"
fi
echo ""

# Test 2: Quality Trends
echo -e "${YELLOW}[2/7] Testing Quality Trends...${NC}"
response=$(curl -s -w "\n%{http_code}" \
    "$BASE_URL/admin/dashboard/trends?days=7" \
    -H "Authorization: Bearer $TOKEN")

status_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}✓ Quality trends retrieved${NC}"
    trend_count=$(echo "$body" | jq -r '.trends | length')
    echo "  Found $trend_count days of trend data"
else
    echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
    echo "$body"
fi
echo ""

# Test 3: Trigger Gap Detection
echo -e "${YELLOW}[3/7] Testing Knowledge Gap Detection...${NC}"
response=$(curl -s -w "\n%{http_code}" \
    -X POST "$BASE_URL/admin/gaps/detect?days=7" \
    -H "Authorization: Bearer $TOKEN")

status_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}✓ Gap detection triggered${NC}"
    gaps_detected=$(echo "$body" | jq -r '.gaps_detected')
    echo "  Detected $gaps_detected knowledge gaps"

    # Save first gap ID for later tests
    GAP_ID=$(echo "$body" | jq -r '.gaps[0].id // empty')
else
    echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
    echo "$body"
fi
echo ""

# Test 4: List Knowledge Gaps
echo -e "${YELLOW}[4/7] Testing List Knowledge Gaps...${NC}"
response=$(curl -s -w "\n%{http_code}" \
    "$BASE_URL/admin/gaps?status=detected&limit=10" \
    -H "Authorization: Bearer $TOKEN")

status_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}✓ Knowledge gaps listed${NC}"
    gap_count=$(echo "$body" | jq -r '.count')
    echo "  Found $gap_count detected gaps"

    # Save a gap ID if we don't have one yet
    if [ -z "$GAP_ID" ]; then
        GAP_ID=$(echo "$body" | jq -r '.gaps[0].id // empty')
    fi
else
    echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
    echo "$body"
fi
echo ""

# Test 5: Acknowledge Gap (only if we have a gap ID)
if [ -n "$GAP_ID" ]; then
    echo -e "${YELLOW}[5/7] Testing Gap Acknowledgment...${NC}"
    response=$(curl -s -w "\n%{http_code}" \
        -X PATCH "$BASE_URL/admin/gaps/$GAP_ID/acknowledge" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"notes": "Test acknowledgment from automated test"}')

    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$status_code" = "200" ]; then
        echo -e "${GREEN}✓ Gap acknowledged successfully${NC}"
        echo "  Gap ID: $GAP_ID"
    else
        echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
        echo "$body"
    fi
else
    echo -e "${YELLOW}[5/7] Skipping Gap Acknowledgment (no gaps found)${NC}"
fi
echo ""

# Test 6: Resolve Gap (only if we have a gap ID)
if [ -n "$GAP_ID" ]; then
    echo -e "${YELLOW}[6/7] Testing Gap Resolution...${NC}"
    response=$(curl -s -w "\n%{http_code}" \
        -X PATCH "$BASE_URL/admin/gaps/$GAP_ID/resolve" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"resolution_notes": "Resolved during automated testing"}')

    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$status_code" = "200" ]; then
        echo -e "${GREEN}✓ Gap resolved successfully${NC}"
        echo "  Gap ID: $GAP_ID"
    else
        echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
        echo "$body"
    fi
else
    echo -e "${YELLOW}[6/7] Skipping Gap Resolution (no gaps found)${NC}"
fi
echo ""

# Test 7: CSV Export
echo -e "${YELLOW}[7/7] Testing CSV Export...${NC}"
response=$(curl -s -w "\n%{http_code}" \
    "$BASE_URL/admin/export/quality-report?days=30&format=csv" \
    -H "Authorization: Bearer $TOKEN" \
    -o /tmp/quality-report-test.csv)

status_code=$(echo "$response" | tail -n1)

if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}✓ CSV export successful${NC}"
    line_count=$(wc -l < /tmp/quality-report-test.csv)
    echo "  Downloaded CSV with $line_count lines"
    echo "  File saved: /tmp/quality-report-test.csv"

    # Show first few lines
    echo "  Preview:"
    head -n 3 /tmp/quality-report-test.csv | sed 's/^/    /'
else
    echo -e "${RED}✗ Failed (HTTP $status_code)${NC}"
fi
echo ""

# Summary
echo "========================================="
echo -e "${GREEN}Phase 4 Testing Complete${NC}"
echo "========================================="
echo ""
echo "Features Tested:"
echo "  ✓ Dashboard Overview"
echo "  ✓ Quality Trends"
echo "  ✓ Knowledge Gap Detection"
echo "  ✓ List Knowledge Gaps"
if [ -n "$GAP_ID" ]; then
    echo "  ✓ Acknowledge Gap"
    echo "  ✓ Resolve Gap"
else
    echo "  - Acknowledge Gap (skipped - no gaps)"
    echo "  - Resolve Gap (skipped - no gaps)"
fi
echo "  ✓ CSV Export"
echo ""
echo "Review the test output above for any failures."
echo "Check /tmp/quality-report-test.csv for exported data."
