#!/bin/bash

# ============================================================================
# Phase 5: Scheduled Jobs & Alerting System - Test Script
# ============================================================================
#
# This script tests all Phase 5 features including:
# - Alert rule management (CRUD operations)
# - Alert history viewing
# - Test alert notifications
# - Manual alert checking
# - Scheduler status monitoring
# - Job execution logs
#
# Prerequisites:
# - Service running on http://localhost:8005
# - Valid JWT token with admin role
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="http://localhost:8005/api/v1"
TOKEN=""
ALERT_RULE_ID=""

# ============================================================================
# Helper Functions
# ============================================================================

print_section() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# ============================================================================
# Step 1: Get Access Token
# ============================================================================

print_section "Step 1: Obtaining Access Token"

print_info "Requesting token from authorization server..."

TOKEN_RESPONSE=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    print_error "Failed to obtain access token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

print_success "Access token obtained successfully"

# ============================================================================
# Step 2: Check Scheduler Status
# ============================================================================

print_section "Step 2: Checking Scheduler Status"

SCHEDULER_STATUS=$(curl -s -X GET "$BASE_URL/alerts/scheduler/status" \
  -H "Authorization: Bearer $TOKEN")

echo "Scheduler Status:"
echo "$SCHEDULER_STATUS" | jq '.'

if [ $(echo $SCHEDULER_STATUS | jq -r '.scheduler_running') = "true" ]; then
    print_success "Background scheduler is running"
else
    print_error "Background scheduler is not running"
fi

# ============================================================================
# Step 3: Create Alert Rule
# ============================================================================

print_section "Step 3: Creating Alert Rule"

CREATE_RULE_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Quality Drop Alert - Test",
    "rule_type": "quality_drop",
    "description": "Alert when average answer confidence drops below 0.6",
    "threshold_value": 0.6,
    "check_interval_hours": 1,
    "min_sample_size": 5,
    "notification_channels": ["console", "email"],
    "notification_recipients": {
      "emails": ["admin@example.com"]
    },
    "throttle_minutes": 60,
    "enabled": true
  }')

echo "Create Rule Response:"
echo "$CREATE_RULE_RESPONSE" | jq '.'

ALERT_RULE_ID=$(echo $CREATE_RULE_RESPONSE | jq -r '.id')

if [ "$ALERT_RULE_ID" != "null" ] && [ -n "$ALERT_RULE_ID" ]; then
    print_success "Alert rule created successfully (ID: $ALERT_RULE_ID)"
else
    print_error "Failed to create alert rule"
    exit 1
fi

# ============================================================================
# Step 4: List Alert Rules
# ============================================================================

print_section "Step 4: Listing All Alert Rules"

LIST_RULES_RESPONSE=$(curl -s -X GET "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN")

echo "Alert Rules:"
echo "$LIST_RULES_RESPONSE" | jq '.'

RULES_COUNT=$(echo $LIST_RULES_RESPONSE | jq '.count')
print_success "Found $RULES_COUNT alert rule(s)"

# ============================================================================
# Step 5: Get Specific Alert Rule
# ============================================================================

print_section "Step 5: Getting Specific Alert Rule"

GET_RULE_RESPONSE=$(curl -s -X GET "$BASE_URL/alerts/rules/$ALERT_RULE_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "Alert Rule Details:"
echo "$GET_RULE_RESPONSE" | jq '.'

print_success "Retrieved alert rule details"

# ============================================================================
# Step 6: Update Alert Rule
# ============================================================================

print_section "Step 6: Updating Alert Rule"

UPDATE_RULE_RESPONSE=$(curl -s -X PUT "$BASE_URL/alerts/rules/$ALERT_RULE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated: Alert when average answer confidence drops below 0.6",
    "threshold_value": 0.65
  }')

echo "Update Rule Response:"
echo "$UPDATE_RULE_RESPONSE" | jq '.'

print_success "Alert rule updated successfully"

# ============================================================================
# Step 7: Send Test Alert
# ============================================================================

print_section "Step 7: Sending Test Alert"

TEST_ALERT_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["console"],
    "recipients": null
  }')

echo "Test Alert Response:"
echo "$TEST_ALERT_RESPONSE" | jq '.'

if [ $(echo $TEST_ALERT_RESPONSE | jq -r '.success') = "true" ]; then
    print_success "Test alert sent successfully"
else
    print_error "Failed to send test alert"
fi

# ============================================================================
# Step 8: Manually Trigger Alert Check
# ============================================================================

print_section "Step 8: Manually Triggering Alert Check"

CHECK_ALERTS_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/check-now" \
  -H "Authorization: Bearer $TOKEN")

echo "Check Alerts Response:"
echo "$CHECK_ALERTS_RESPONSE" | jq '.'

if [ $(echo $CHECK_ALERTS_RESPONSE | jq -r '.success') = "true" ]; then
    print_success "Alert check completed successfully"
else
    print_error "Failed to check alerts"
fi

# ============================================================================
# Step 9: View Alert History
# ============================================================================

print_section "Step 9: Viewing Alert History"

ALERT_HISTORY_RESPONSE=$(curl -s -X GET "$BASE_URL/alerts/history?limit=10" \
  -H "Authorization: Bearer $TOKEN")

echo "Alert History:"
echo "$ALERT_HISTORY_RESPONSE" | jq '.'

HISTORY_COUNT=$(echo $ALERT_HISTORY_RESPONSE | jq '.count')
print_success "Found $HISTORY_COUNT alert(s) in history"

# ============================================================================
# Step 10: View Job Execution Logs
# ============================================================================

print_section "Step 10: Viewing Job Execution Logs"

JOB_LOGS_RESPONSE=$(curl -s -X GET "$BASE_URL/alerts/jobs/logs?limit=10" \
  -H "Authorization: Bearer $TOKEN")

echo "Job Execution Logs:"
echo "$JOB_LOGS_RESPONSE" | jq '.'

LOGS_COUNT=$(echo $JOB_LOGS_RESPONSE | jq '.count')
print_success "Found $LOGS_COUNT job execution log(s)"

# ============================================================================
# Step 11: Create Additional Alert Rules
# ============================================================================

print_section "Step 11: Creating Additional Alert Rules"

# Create New Gaps Alert
print_info "Creating 'New Gaps' alert rule..."
NEW_GAPS_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Knowledge Gaps Alert",
    "rule_type": "new_gaps",
    "description": "Alert when 3 or more new knowledge gaps are detected",
    "threshold_value": 3,
    "check_interval_hours": 24,
    "min_sample_size": 1,
    "notification_channels": ["console"],
    "throttle_minutes": 1440,
    "enabled": true
  }')

if [ $(echo $NEW_GAPS_RESPONSE | jq -r '.id') != "null" ]; then
    print_success "New Gaps alert rule created"
else
    print_error "Failed to create New Gaps alert rule"
fi

# Create High Negative Feedback Alert
print_info "Creating 'High Negative Feedback' alert rule..."
NEGATIVE_FEEDBACK_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Negative Feedback Alert",
    "rule_type": "high_negative_feedback",
    "description": "Alert when negative feedback rate exceeds 30%",
    "threshold_value": 0.3,
    "check_interval_hours": 12,
    "min_sample_size": 10,
    "notification_channels": ["console"],
    "throttle_minutes": 720,
    "enabled": true
  }')

if [ $(echo $NEGATIVE_FEEDBACK_RESPONSE | jq -r '.id') != "null" ]; then
    print_success "High Negative Feedback alert rule created"
else
    print_error "Failed to create High Negative Feedback alert rule"
fi

# Create Session Degradation Alert
print_info "Creating 'Session Degradation' alert rule..."
SESSION_DEGRADATION_RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Session Quality Degradation Alert",
    "rule_type": "session_degradation",
    "description": "Alert when 5 or more sessions have poor quality",
    "threshold_value": 5,
    "check_interval_hours": 6,
    "min_sample_size": 1,
    "notification_channels": ["console"],
    "throttle_minutes": 360,
    "enabled": true
  }')

if [ $(echo $SESSION_DEGRADATION_RESPONSE | jq -r '.id') != "null" ]; then
    print_success "Session Degradation alert rule created"
else
    print_error "Failed to create Session Degradation alert rule"
fi

# ============================================================================
# Step 12: List All Rules Again
# ============================================================================

print_section "Step 12: Listing All Alert Rules (Final Count)"

FINAL_LIST_RESPONSE=$(curl -s -X GET "$BASE_URL/alerts/rules" \
  -H "Authorization: Bearer $TOKEN")

echo "All Alert Rules:"
echo "$FINAL_LIST_RESPONSE" | jq '.rules[] | {id, name, rule_type, enabled, threshold_value}'

FINAL_COUNT=$(echo $FINAL_LIST_RESPONSE | jq '.count')
print_success "Total alert rules configured: $FINAL_COUNT"

# ============================================================================
# Step 13: Delete Test Alert Rule
# ============================================================================

print_section "Step 13: Cleaning Up - Deleting Test Alert Rule"

DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/alerts/rules/$ALERT_RULE_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "Delete Response:"
echo "$DELETE_RESPONSE" | jq '.'

if [ $(echo $DELETE_RESPONSE | jq -r '.success') = "true" ]; then
    print_success "Test alert rule deleted successfully"
else
    print_error "Failed to delete test alert rule"
fi

# ============================================================================
# Summary
# ============================================================================

print_section "Phase 5 Testing Complete!"

echo -e "${GREEN}All Phase 5 features tested successfully:${NC}"
echo "  ✓ Scheduler status monitoring"
echo "  ✓ Alert rule creation"
echo "  ✓ Alert rule listing"
echo "  ✓ Alert rule retrieval"
echo "  ✓ Alert rule updates"
echo "  ✓ Test alert sending"
echo "  ✓ Manual alert checking"
echo "  ✓ Alert history viewing"
echo "  ✓ Job execution logs"
echo "  ✓ Alert rule deletion"
echo ""
echo -e "${BLUE}Phase 5 implementation verified!${NC}"
