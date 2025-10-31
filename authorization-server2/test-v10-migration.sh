#!/bin/bash
# =====================================================================================
# Test Script for V10 Migration
# =====================================================================================
# This script tests the V10 migration in a safe way before deploying to production
# =====================================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Database configuration (update these for your environment)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-authorization_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-password}"

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}V10 Migration Test Script${NC}"
echo -e "${BLUE}==================================================================${NC}"
echo ""

# Function to run SQL and show results
run_sql() {
    local query="$1"
    local description="$2"

    echo -e "${YELLOW}Testing: ${description}${NC}"
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c "${query}"
    echo ""
}

# Function to check if migration V10 has run
check_migration_status() {
    echo -e "${YELLOW}1. Checking Migration Status${NC}"
    echo "----------------------------------------"

    local v10_status=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c "SELECT COUNT(*) FROM flyway_schema_history WHERE version = '10';")

    if [ "$v10_status" -eq 1 ]; then
        echo -e "${GREEN}✓ V10 migration has been applied${NC}"

        # Show migration details
        PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c \
            "SELECT version, description, installed_on, success FROM flyway_schema_history WHERE version = '10';"
    else
        echo -e "${YELLOW}⚠ V10 migration has not been applied yet${NC}"
        echo "Run the application to apply migrations, or run: mvn flyway:migrate"
    fi
    echo ""
}

# Function to check roles
check_roles() {
    echo -e "${YELLOW}2. Checking Roles${NC}"
    echo "----------------------------------------"

    run_sql "SELECT id, name, description, is_active, created_at FROM roles WHERE name IN ('TENANT_ADMIN', 'SYSTEM_ADMIN') ORDER BY name;" \
        "Required system roles"

    # Count total roles
    local role_count=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c "SELECT COUNT(*) FROM roles WHERE is_active = true;")
    echo -e "Total active roles: ${GREEN}${role_count}${NC}"
    echo ""
}

# Function to check registered clients
check_registered_clients() {
    echo -e "${YELLOW}3. Checking Registered Clients URLs${NC}"
    echo "----------------------------------------"

    run_sql "SELECT client_id, client_name, redirect_uris, post_logout_redirect_uris, is_active FROM registered_clients ORDER BY client_id;" \
        "All registered OAuth2 clients"

    # Check for localhost URLs
    local localhost_count=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM registered_clients WHERE (redirect_uris LIKE '%localhost%' OR post_logout_redirect_uris LIKE '%localhost%') AND is_active = true;")

    if [ "$localhost_count" -eq 0 ]; then
        echo -e "${GREEN}✓ No localhost URLs found in active clients (production ready)${NC}"
    else
        echo -e "${RED}✗ Found ${localhost_count} active client(s) with localhost URLs${NC}"
        echo -e "${YELLOW}These need to be updated to production URLs${NC}"

        # Show which clients have localhost
        run_sql "SELECT client_id, redirect_uris, post_logout_redirect_uris FROM registered_clients WHERE (redirect_uris LIKE '%localhost%' OR post_logout_redirect_uris LIKE '%localhost%') AND is_active = true;" \
            "Clients with localhost URLs"
    fi
    echo ""
}

# Function to check production URLs
check_production_urls() {
    echo -e "${YELLOW}4. Checking Production URLs${NC}"
    echo "----------------------------------------"

    local prod_count=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM registered_clients WHERE (redirect_uris LIKE '%app.chatcraft.cc%' OR post_logout_redirect_uris LIKE '%app.chatcraft.cc%') AND is_active = true;")

    if [ "$prod_count" -gt 0 ]; then
        echo -e "${GREEN}✓ Found ${prod_count} active client(s) with production URLs (app.chatcraft.cc)${NC}"
    else
        echo -e "${YELLOW}⚠ No clients configured with production URLs yet${NC}"
    fi
    echo ""
}

# Function to show summary
show_summary() {
    echo -e "${BLUE}==================================================================${NC}"
    echo -e "${BLUE}Summary${NC}"
    echo -e "${BLUE}==================================================================${NC}"

    # Check if everything is ready for production
    local v10_exists=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM flyway_schema_history WHERE version = '10';")

    local system_admin_exists=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM roles WHERE name = 'SYSTEM_ADMIN';")

    local tenant_admin_exists=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM roles WHERE name = 'TENANT_ADMIN';")

    local localhost_count=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM registered_clients WHERE (redirect_uris LIKE '%localhost%' OR post_logout_redirect_uris LIKE '%localhost%') AND is_active = true;")

    local prod_count=$(PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT COUNT(*) FROM registered_clients WHERE (redirect_uris LIKE '%app.chatcraft.cc%' OR post_logout_redirect_uris LIKE '%app.chatcraft.cc%') AND is_active = true;")

    echo ""
    echo "Migration Status:"
    [ "$v10_exists" -eq 1 ] && echo -e "  ${GREEN}✓${NC} V10 migration applied" || echo -e "  ${RED}✗${NC} V10 migration not applied"

    echo ""
    echo "Roles Status:"
    [ "$system_admin_exists" -eq 1 ] && echo -e "  ${GREEN}✓${NC} SYSTEM_ADMIN role exists" || echo -e "  ${RED}✗${NC} SYSTEM_ADMIN role missing"
    [ "$tenant_admin_exists" -eq 1 ] && echo -e "  ${GREEN}✓${NC} TENANT_ADMIN role exists" || echo -e "  ${RED}✗${NC} TENANT_ADMIN role missing"

    echo ""
    echo "OAuth2 Clients Status:"
    [ "$localhost_count" -eq 0 ] && echo -e "  ${GREEN}✓${NC} No localhost URLs (production ready)" || echo -e "  ${YELLOW}⚠${NC} ${localhost_count} client(s) still have localhost URLs"
    [ "$prod_count" -gt 0 ] && echo -e "  ${GREEN}✓${NC} ${prod_count} client(s) configured with production URLs" || echo -e "  ${YELLOW}⚠${NC} No production URLs configured"

    echo ""

    # Overall status
    if [ "$v10_exists" -eq 1 ] && [ "$system_admin_exists" -eq 1 ] && [ "$tenant_admin_exists" -eq 1 ] && [ "$localhost_count" -eq 0 ] && [ "$prod_count" -gt 0 ]; then
        echo -e "${GREEN}==================================================================${NC}"
        echo -e "${GREEN}✓ Database is READY for production deployment${NC}"
        echo -e "${GREEN}==================================================================${NC}"
    else
        echo -e "${YELLOW}==================================================================${NC}"
        echo -e "${YELLOW}⚠ Database needs attention before production deployment${NC}"
        echo -e "${YELLOW}==================================================================${NC}"

        if [ "$v10_exists" -eq 0 ]; then
            echo -e "${YELLOW}Action needed: Run the application to apply V10 migration${NC}"
        fi

        if [ "$localhost_count" -gt 0 ]; then
            echo -e "${YELLOW}Action needed: Run V10 migration to update client URLs${NC}"
        fi
    fi

    echo ""
}

# Main execution
main() {
    echo "Testing database: ${DB_NAME} on ${DB_HOST}:${DB_PORT}"
    echo "User: ${DB_USER}"
    echo ""

    # Test database connection
    echo -e "${YELLOW}Testing database connection...${NC}"
    if PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Database connection successful${NC}"
        echo ""
    else
        echo -e "${RED}✗ Cannot connect to database${NC}"
        echo "Please check your database configuration and try again."
        exit 1
    fi

    # Run checks
    check_migration_status
    check_roles
    check_registered_clients
    check_production_urls
    show_summary
}

# Run main function
main
