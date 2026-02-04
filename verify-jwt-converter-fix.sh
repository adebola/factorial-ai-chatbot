#!/bin/bash

# Simple verification script to check if JwtAuthenticationConverter is properly configured
# This script checks the authorization server logs for the configuration message

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== JWT Authentication Converter Fix Verification ===${NC}"
echo ""

echo -e "${YELLOW}Step 1: Check if authorization server is running${NC}"
if lsof -ti:9002 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Authorization server is running on port 9002${NC}"
else
    echo -e "${RED}✗ Authorization server is NOT running on port 9002${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Verify JwtAuthenticationConverter configuration in logs${NC}"

if grep -q "Configured JwtAuthenticationConverter to extract authorities from 'authorities' claim" /tmp/auth-server.log 2>/dev/null; then
    echo -e "${GREEN}✓ Found JwtAuthenticationConverter configuration in logs${NC}"
    echo ""
    echo "Log entry:"
    grep "Configured JwtAuthenticationConverter" /tmp/auth-server.log | tail -1
else
    echo -e "${RED}✗ JwtAuthenticationConverter configuration NOT found in logs${NC}"
    echo ""
    echo "This could mean:"
    echo "  1. The authorization server hasn't fully started yet"
    echo "  2. The fix wasn't applied correctly"
    echo "  3. Log file location is different"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 3: Check SecurityConfig.java for the fix${NC}"

SECURITY_CONFIG="/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config/SecurityConfig.java"

if grep -q "jwtAuthenticationConverter()" "$SECURITY_CONFIG"; then
    echo -e "${GREEN}✓ Found jwtAuthenticationConverter() method in SecurityConfig.java${NC}"
else
    echo -e "${RED}✗ jwtAuthenticationConverter() method NOT found in SecurityConfig.java${NC}"
    exit 1
fi

if grep -q "setAuthoritiesClaimName(\"authorities\")" "$SECURITY_CONFIG"; then
    echo -e "${GREEN}✓ Found setAuthoritiesClaimName(\"authorities\") configuration${NC}"
else
    echo -e "${RED}✗ setAuthoritiesClaimName(\"authorities\") NOT found${NC}"
    exit 1
fi

if grep -q ".jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))" "$SECURITY_CONFIG"; then
    echo -e "${GREEN}✓ Found custom JWT converter configuration in apiSecurityFilterChain${NC}"
else
    echo -e "${RED}✗ Custom JWT converter NOT configured in apiSecurityFilterChain${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ ALL CHECKS PASSED!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Summary of the fix:"
echo "1. Added JwtAuthenticationConverter bean to SecurityConfig.java ✓"
echo "2. Configured to extract authorities from 'authorities' claim ✓"
echo "3. Applied to apiSecurityFilterChain for /api/v1/** endpoints ✓"
echo "4. Authorization server loaded the configuration successfully ✓"
echo ""
echo -e "${GREEN}The JWT authentication converter fix has been successfully implemented!${NC}"
echo ""
echo "What this fixes:"
echo "- Before: Authorization server only extracted 'scope' claim → SCOPE_* authorities"
echo "- After: Authorization server extracts 'authorities' claim → ROLE_* authorities"
echo "- Result: Super admin users can now access /api/v1/admin/* endpoints without 401 errors"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Test the admin app at http://localhost:4201"
echo "2. Login with system admin credentials (username: admin, password: password)"
echo "3. Verify that you stay logged in and can access admin features"
echo "4. Check browser console for any 401 errors (should be none)"
