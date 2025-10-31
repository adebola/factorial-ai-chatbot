#!/bin/bash

# =====================================================
# RDS MIGRATION VALIDATION SCRIPT
# =====================================================
# Purpose: Validate RDS migration completeness and correctness
# Author: Auto-generated RDS Migration Script
# Date: 2025-10-27
# =====================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
RDS_HOST="${RDS_HOST}"
RDS_PORT="${RDS_PORT:-5432}"
RDS_USER="${RDS_USER:-postgres}"
RDS_PASSWORD="${RDS_PASSWORD}"

VALIDATION_LOG="validation_$(date +%Y%m%d_%H%M%S).log"

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# =====================================================
# HELPER FUNCTIONS
# =====================================================

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$VALIDATION_LOG"
}

pass() {
    echo -e "${GREEN}✓ PASS${NC} $1" | tee -a "$VALIDATION_LOG"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC} $1" | tee -a "$VALIDATION_LOG"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC} $1" | tee -a "$VALIDATION_LOG"
    ((WARNINGS++))
}

section() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}=========================================${NC}"
    log "Starting validation: $1"
}

run_query() {
    local db=$1
    local query=$2
    export PGPASSWORD="$RDS_PASSWORD"
    psql -h "$RDS_HOST" -p "$RDS_PORT" -U "$RDS_USER" -d "$db" -tAc "$query" 2>/dev/null
}

# =====================================================
# VALIDATION CHECKS
# =====================================================

validate_connectivity() {
    section "1. Connectivity Checks"

    log "Testing RDS connectivity..."
    if run_query "postgres" "SELECT 1" > /dev/null 2>&1; then
        pass "RDS connectivity established"
    else
        fail "Cannot connect to RDS at $RDS_HOST:$RDS_PORT"
        return 1
    fi
}

validate_databases() {
    section "2. Database Existence"

    local databases=(
        "vector_db"
        "chatbot_db"
        "onboard_db"
        "authorization_db"
        "communications_db"
        "billing_db"
        "workflow_db"
        "answer_quality_db"
    )

    for db in "${databases[@]}"; do
        local exists=$(run_query "postgres" "SELECT 1 FROM pg_database WHERE datname='$db'")
        if [ "$exists" = "1" ]; then
            pass "Database $db exists"
        else
            fail "Database $db does not exist"
        fi
    done
}

validate_extensions() {
    section "3. PostgreSQL Extensions"

    # Check uuid-ossp in all databases
    local databases=("vector_db" "chatbot_db" "onboard_db" "authorization_db" "communications_db" "billing_db" "workflow_db" "answer_quality_db")

    for db in "${databases[@]}"; do
        local has_uuid=$(run_query "$db" "SELECT 1 FROM pg_extension WHERE extname='uuid-ossp'")
        if [ "$has_uuid" = "1" ]; then
            pass "Extension uuid-ossp installed in $db"
        else
            fail "Extension uuid-ossp not found in $db"
        fi
    done

    # Check pgvector in vector_db
    local has_vector=$(run_query "vector_db" "SELECT 1 FROM pg_extension WHERE extname='vector'")
    if [ "$has_vector" = "1" ]; then
        pass "Extension pgvector installed in vector_db"
    else
        fail "Extension pgvector not found in vector_db"
    fi
}

validate_schemas() {
    section "4. Schema Validation"

    # Check vectors schema in vector_db
    local has_vectors_schema=$(run_query "vector_db" "SELECT 1 FROM information_schema.schemata WHERE schema_name='vectors'")
    if [ "$has_vectors_schema" = "1" ]; then
        pass "Schema 'vectors' exists in vector_db"
    else
        fail "Schema 'vectors' not found in vector_db"
    fi
}

validate_tables() {
    section "5. Table Validation"

    # Vector DB tables
    local vector_tables=("vectors.document_chunks" "vectors.vector_search_indexes")
    for table in "${vector_tables[@]}"; do
        local count=$(run_query "vector_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='vectors' AND table_name='${table##*.}'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists"
        else
            fail "Table $table not found"
        fi
    done

    # Chat Service tables
    local chat_tables=("chat_sessions" "chat_messages")
    for table in "${chat_tables[@]}"; do
        local count=$(run_query "chatbot_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in chatbot_db"
        else
            fail "Table $table not found in chatbot_db"
        fi
    done

    # Authorization Server tables
    local auth_tables=("tenants" "users" "roles" "user_roles" "registered_clients" "tenant_settings" "verification_tokens")
    for table in "${auth_tables[@]}"; do
        local count=$(run_query "authorization_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in authorization_db"
        else
            fail "Table $table not found in authorization_db"
        fi
    done

    # Onboarding Service tables
    local onboard_tables=("documents" "website_ingestions" "website_pages" "subscriptions" "payments")
    for table in "${onboard_tables[@]}"; do
        local count=$(run_query "onboard_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in onboard_db"
        else
            fail "Table $table not found in onboard_db"
        fi
    done

    # Communications Service tables
    local comm_tables=("email_messages" "sms_messages" "message_templates")
    for table in "${comm_tables[@]}"; do
        local count=$(run_query "communications_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in communications_db"
        else
            fail "Table $table not found in communications_db"
        fi
    done

    # Billing Service tables
    local billing_tables=("plans")
    for table in "${billing_tables[@]}"; do
        local count=$(run_query "billing_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in billing_db"
        else
            fail "Table $table not found in billing_db"
        fi
    done

    # Workflow Service tables
    local workflow_tables=("workflows" "workflow_executions" "workflow_states")
    for table in "${workflow_tables[@]}"; do
        local count=$(run_query "workflow_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in workflow_db"
        else
            fail "Table $table not found in workflow_db"
        fi
    done

    # Answer Quality Service tables
    local quality_tables=("answer_feedback" "rag_quality_metrics" "session_quality" "knowledge_gaps")
    for table in "${quality_tables[@]}"; do
        local count=$(run_query "answer_quality_db" "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='$table'")
        if [ "$count" -ge 1 ]; then
            pass "Table $table exists in answer_quality_db"
        else
            fail "Table $table not found in answer_quality_db"
        fi
    done
}

validate_indexes() {
    section "6. Index Validation"

    # Check critical indexes
    local vector_index=$(run_query "vector_db" "SELECT 1 FROM pg_indexes WHERE schemaname='vectors' AND indexname='idx_chunks_tenant_embedding'")
    if [ "$vector_index" = "1" ]; then
        pass "IVFFlat vector index exists"
    else
        fail "IVFFlat vector index not found"
    fi

    # Count total indexes in vector_db
    local index_count=$(run_query "vector_db" "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='vectors'")
    if [ "$index_count" -ge 5 ]; then
        pass "Vector database has $index_count indexes"
    else
        warn "Vector database has only $index_count indexes (expected at least 5)"
    fi
}

validate_vector_dimensions() {
    section "7. Vector Dimension Validation"

    # Create a test record if table is empty
    local chunk_count=$(run_query "vector_db" "SELECT COUNT(*) FROM vectors.document_chunks")

    if [ "$chunk_count" -eq 0 ]; then
        warn "No chunks in document_chunks table (skipping dimension check)"
    else
        local dimensions=$(run_query "vector_db" "SELECT vector_dims(embedding) FROM vectors.document_chunks LIMIT 1")
        if [ "$dimensions" = "1536" ]; then
            pass "Vector embeddings have correct dimensions (1536)"
        else
            fail "Vector embeddings have incorrect dimensions ($dimensions, expected 1536)"
        fi
    fi
}

validate_default_data() {
    section "8. Default Data Validation"

    # Check if default plans exist in billing_db
    local plan_count=$(run_query "billing_db" "SELECT COUNT(*) FROM plans WHERE is_active=true")
    if [ "$plan_count" -ge 4 ]; then
        pass "Default plans seeded ($plan_count plans found)"
    else
        warn "Only $plan_count active plans found (expected at least 4)"
    fi

    # List plan names
    local plans=$(run_query "billing_db" "SELECT name FROM plans WHERE is_active=true ORDER BY monthly_plan_cost")
    log "Active plans: $plans"

    # Check if default roles exist in authorization_db
    local role_count=$(run_query "authorization_db" "SELECT COUNT(*) FROM roles")
    if [ "$role_count" -ge 3 ]; then
        pass "Default roles seeded ($role_count roles found)"
    else
        warn "Only $role_count roles found (expected at least 3)"
    fi

    # Check if default users exist
    local user_count=$(run_query "authorization_db" "SELECT COUNT(*) FROM users")
    if [ "$user_count" -ge 2 ]; then
        pass "Default users seeded ($user_count users found)"
    else
        warn "Only $user_count users found (expected at least 2)"
    fi

    # Check if default OAuth2 client exists
    local client_count=$(run_query "authorization_db" "SELECT COUNT(*) FROM registered_clients WHERE client_id='webclient'")
    if [ "$client_count" -ge 1 ]; then
        pass "Default OAuth2 client seeded"
    else
        warn "Default OAuth2 client not found"
    fi
}

validate_triggers() {
    section "9. Trigger Validation"

    # Check update triggers exist
    local trigger_count=$(run_query "vector_db" "SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'update_%_updated_at'")
    if [ "$trigger_count" -ge 1 ]; then
        pass "Update triggers exist in vector_db"
    else
        warn "No update triggers found in vector_db"
    fi
}

validate_alembic_versions() {
    section "10. Alembic/Flyway Migration Validation"

    # Check Alembic version tables
    local alembic_databases=("communications_db" "workflow_db" "billing_db" "answer_quality_db" "onboard_db")

    for db in "${alembic_databases[@]}"; do
        local has_alembic=$(run_query "$db" "SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version'")
        if [ "$has_alembic" = "1" ]; then
            local version=$(run_query "$db" "SELECT version_num FROM alembic_version")
            if [ -n "$version" ]; then
                pass "Alembic version $version applied to $db"
            else
                warn "Alembic version table exists but no version recorded in $db"
            fi
        else
            warn "Alembic version table not found in $db (migrations may not have run)"
        fi
    done

    # Check Flyway schema history (authorization_db)
    local has_flyway=$(run_query "authorization_db" "SELECT 1 FROM information_schema.tables WHERE table_name='flyway_schema_history'")
    if [ "$has_flyway" = "1" ]; then
        local version=$(run_query "authorization_db" "SELECT version FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 1")
        if [ -n "$version" ]; then
            pass "Flyway version $version applied to authorization_db"
        else
            warn "Flyway schema history exists but no version recorded"
        fi
    else
        warn "Flyway schema history not found in authorization_db"
    fi
}

validate_constraints() {
    section "11. Constraint Validation"

    # Check foreign keys exist
    local fk_count=$(run_query "onboard_db" "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY'")
    if [ "$fk_count" -ge 5 ]; then
        pass "Foreign key constraints exist in onboard_db ($fk_count found)"
    else
        warn "Only $fk_count foreign key constraints in onboard_db"
    fi

    # Check unique constraints
    local unique_count=$(run_query "billing_db" "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type='UNIQUE'")
    if [ "$unique_count" -ge 1 ]; then
        pass "Unique constraints exist in billing_db ($unique_count found)"
    else
        warn "No unique constraints found in billing_db"
    fi
}

validate_row_counts() {
    section "12. Data Migration Validation"

    log "Checking row counts in key tables..."

    local databases=("vector_db" "chatbot_db" "onboard_db" "communications_db" "workflow_db" "answer_quality_db")

    for db in "${databases[@]}"; do
        local total_rows=$(run_query "$db" "SELECT SUM(n_live_tup)::int FROM pg_stat_user_tables")
        if [ -n "$total_rows" ] && [ "$total_rows" -gt 0 ]; then
            pass "Database $db has $total_rows total rows"
        else
            warn "Database $db appears empty (0 rows)"
        fi
    done
}

validate_performance() {
    section "13. Performance Validation"

    # Check if indexes are being used
    local index_scans=$(run_query "vector_db" "SELECT SUM(idx_scan)::int FROM pg_stat_user_indexes WHERE schemaname='vectors'")
    if [ -n "$index_scans" ]; then
        log "Vector indexes have been scanned $index_scans times"
    fi

    # Check for bloat
    local bloated_tables=$(run_query "vector_db" "SELECT COUNT(*) FROM pg_stat_user_tables WHERE n_dead_tup > n_live_tup")
    if [ "$bloated_tables" -gt 0 ]; then
        warn "$bloated_tables tables may have significant bloat - consider VACUUM ANALYZE"
    else
        pass "No significant table bloat detected"
    fi
}

# =====================================================
# MAIN EXECUTION
# =====================================================

main() {
    log "========================================="
    log "RDS MIGRATION VALIDATION"
    log "========================================="
    log "RDS Host: $RDS_HOST"
    log "RDS Port: $RDS_PORT"
    log "RDS User: $RDS_USER"
    log "Validation Log: $VALIDATION_LOG"
    log ""

    if [ -z "$RDS_HOST" ] || [ -z "$RDS_PASSWORD" ]; then
        fail "RDS_HOST and RDS_PASSWORD must be set"
        exit 1
    fi

    validate_connectivity
    validate_databases
    validate_extensions
    validate_schemas
    validate_tables
    validate_indexes
    validate_vector_dimensions
    validate_default_data
    validate_triggers
    validate_alembic_versions
    validate_constraints
    validate_row_counts
    validate_performance

    # Summary
    echo ""
    log "========================================="
    log "VALIDATION SUMMARY"
    log "========================================="
    log "Passed:   $PASSED"
    log "Failed:   $FAILED"
    log "Warnings: $WARNINGS"
    log "========================================="

    if [ "$FAILED" -eq 0 ]; then
        log "${GREEN}All critical validations passed!${NC}"
        exit 0
    else
        log "${RED}$FAILED validation(s) failed. Please review.${NC}"
        exit 1
    fi
}

main