#!/bin/bash

##############################################################################
# User Registration Script for Live/Production Environment
#
# This script registers a new tenant (organization) and admin user in the
# FactorialBot production authorization server.
#
# Usage:
#   ./register-user-live.sh
#   (Script will prompt for all required information)
#
# Or with environment variables:
#   ORG_NAME="My Company" \
#   ORG_DOMAIN="mycompany.com" \
#   ADMIN_USERNAME="admin" \
#   ADMIN_EMAIL="admin@mycompany.com" \
#   ADMIN_FIRST_NAME="John" \
#   ADMIN_LAST_NAME="Doe" \
#   ADMIN_PASSWORD="SecurePassword123!" \
#   ./register-user-live.sh
##############################################################################

set -e  # Exit on error

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Production authorization server URL
PROD_URL="${AUTH_SERVER_URL:-https://api.chatcraft.cc}"
REGISTER_ENDPOINT="${PROD_URL}/register"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  FactorialBot User Registration (LIVE)${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will register a user in the PRODUCTION environment!${NC}"
echo -e "${YELLOW}   URL: ${REGISTER_ENDPOINT}${NC}"
echo ""

# Function to read input with default value
read_input() {
    local prompt="$1"
    local var_name="$2"
    local default_value="${!var_name}"

    if [ -n "$default_value" ]; then
        echo -e "${GREEN}Using provided value for ${var_name}: ${default_value}${NC}"
        return
    fi

    read -p "$prompt: " input
    eval "$var_name='$input'"
}

# Function to read password (hidden input)
read_password() {
    local prompt="$1"
    local var_name="$2"
    local default_value="${!var_name}"

    if [ -n "$default_value" ]; then
        echo -e "${GREEN}Using provided password for ${var_name}${NC}"
        return
    fi

    read -s -p "$prompt: " input
    echo ""
    eval "$var_name='$input'"
}

# Collect registration information
echo -e "${BLUE}Organization Information:${NC}"
read_input "Organization Name (e.g., 'Acme Corporation')" ORG_NAME

echo ""
echo -e "${BLUE}Administrator Account:${NC}"
read_input "Admin Username (letters, numbers, _, -)" ADMIN_USERNAME
read_input "Admin Email" ADMIN_EMAIL
read_input "Admin First Name" ADMIN_FIRST_NAME
read_input "Admin Last Name" ADMIN_LAST_NAME
read_password "Admin Password (min 8 characters)" ADMIN_PASSWORD

# Validate required fields
echo ""
echo -e "${BLUE}Validating input...${NC}"

if [ -z "$ORG_NAME" ]; then
    echo -e "${RED}❌ Error: Organization name is required${NC}"
    exit 1
fi

if [ -z "$ADMIN_USERNAME" ]; then
    echo -e "${RED}❌ Error: Admin username is required${NC}"
    exit 1
fi

if [ -z "$ADMIN_EMAIL" ]; then
    echo -e "${RED}❌ Error: Admin email is required${NC}"
    exit 1
fi

if [ -z "$ADMIN_PASSWORD" ]; then
    echo -e "${RED}❌ Error: Admin password is required${NC}"
    exit 1
fi

# Show summary
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Registration Summary${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Organization Name: ${GREEN}${ORG_NAME}${NC}"
echo -e "Admin Username: ${GREEN}${ADMIN_USERNAME}${NC}"
echo -e "Admin Email: ${GREEN}${ADMIN_EMAIL}${NC}"
echo -e "Admin First Name: ${GREEN}${ADMIN_FIRST_NAME}${NC}"
echo -e "Admin Last Name: ${GREEN}${ADMIN_LAST_NAME}${NC}"
echo -e "Password: ${GREEN}***********${NC}"
echo ""
echo -e "${YELLOW}⚠️  Target: ${REGISTER_ENDPOINT}${NC}"
echo ""

# Confirm before proceeding
read -p "Proceed with registration? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}Registration cancelled.${NC}"
    exit 0
fi

# Create JSON payload
JSON_PAYLOAD=$(cat <<EOF
{
  "name": "$ORG_NAME",
  "adminUsername": "$ADMIN_USERNAME",
  "adminEmail": "$ADMIN_EMAIL",
  "adminFirstName": "$ADMIN_FIRST_NAME",
  "adminLastName": "$ADMIN_LAST_NAME",
  "adminPassword": "$ADMIN_PASSWORD"
}
EOF
)

echo ""
echo -e "${BLUE}Sending registration request...${NC}"

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$REGISTER_ENDPOINT" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD")

# Split response body and status code
HTTP_BODY=$(echo "$RESPONSE" | sed '$d')
HTTP_STATUS=$(echo "$RESPONSE" | tail -n1)

echo ""
echo -e "${BLUE}Response Status: ${HTTP_STATUS}${NC}"

# Check response
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "201" ] || [ "$HTTP_STATUS" = "302" ]; then
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  ✓ Registration Successful!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${GREEN}Organization '${ORG_NAME}' has been registered successfully!${NC}"
    echo ""
    echo -e "${YELLOW}📧 A verification email has been sent to: ${ADMIN_EMAIL}${NC}"
    echo -e "${YELLOW}   Please check your inbox and click the verification link to activate your account.${NC}"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Check email inbox for verification link"
    echo "2. Click verification link to activate account"
    echo "3. Login at: ${PROD_URL}/login"
    echo ""
    echo -e "${BLUE}Login Credentials:${NC}"
    echo -e "  Username: ${GREEN}${ADMIN_USERNAME}${NC}"
    echo -e "  Email: ${GREEN}${ADMIN_EMAIL}${NC}"
    echo -e "  Password: ${GREEN}<as provided>${NC}"
    echo ""

    # Save credentials to file (optional)
    CREDS_FILE="registration-${ORG_NAME// /-}-$(date +%Y%m%d-%H%M%S).txt"
    cat > "$CREDS_FILE" <<CREDS
FactorialBot Registration - $(date)
=====================================

Organization: $ORG_NAME

Admin Account:
  Username: $ADMIN_USERNAME
  Email: $ADMIN_EMAIL
  First Name: $ADMIN_FIRST_NAME
  Last Name: $ADMIN_LAST_NAME

Login URL: ${PROD_URL}/login

IMPORTANT: Check email at $ADMIN_EMAIL for verification link
CREDS

    echo -e "${GREEN}✓ Credentials saved to: ${CREDS_FILE}${NC}"
    echo -e "${YELLOW}⚠️  Keep this file secure and delete after verification!${NC}"

else
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  ❌ Registration Failed${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo -e "${RED}HTTP Status: ${HTTP_STATUS}${NC}"
    echo ""
    echo -e "${YELLOW}Response:${NC}"
    echo "$HTTP_BODY"
    echo ""

    # Try to parse common errors
    if echo "$HTTP_BODY" | grep -q "name.taken"; then
        echo -e "${RED}❌ Error: Organization name '${ORG_NAME}' is already taken${NC}"
    elif echo "$HTTP_BODY" | grep -q "username.taken"; then
        echo -e "${RED}❌ Error: Username '${ADMIN_USERNAME}' is already taken${NC}"
    elif echo "$HTTP_BODY" | grep -q "email.taken"; then
        echo -e "${RED}❌ Error: Email '${ADMIN_EMAIL}' is already registered${NC}"
    else
        echo -e "${RED}❌ Registration failed. Please check the response above for details.${NC}"
    fi

    exit 1
fi
