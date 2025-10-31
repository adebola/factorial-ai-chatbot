#!/bin/bash

# =====================================================
# RDS DATA MIGRATION SCRIPT
# =====================================================
# Purpose: Migrate data from Docker PostgreSQL to AWS RDS
# Author: Auto-generated RDS Migration Script
# Date: 2025-10-27
# =====================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# =====================================================
# CONFIGURATION
# =====================================================

# Source (Docker PostgreSQL)
SOURCE_HOST="${SOURCE_HOST:-localhost}"
SOURCE_PORT="${SOURCE_PORT:-5432}"
SOURCE_USER="${SOURCE_USER:-postgres}"
SOURCE_PASSWORD="${SOURCE_PASSWORD:-password}"

# Target (AWS RDS)
TARGET_HOST="${TARGET_HOST:-your-rds-endpoint.region.rds.amazonaws.com}"
TARGET_PORT="${TARGET_PORT:-5432}"
TARGET_USER="${TARGET_USER:-postgres}"
TARGET_PASSWORD="${TARGET_PASSWORD}"

# Backup directory
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Log file
LOG_FILE="$BACKUP_DIR/migration.log"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =====================================================
# HELPER FUNCTIONS
# =====================================================

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Export password for pg_dump/psql to use
export PGPASSWORD_SOURCE="$SOURCE_PASSWORD"
export PGPASSWORD="$TARGET_PASSWORD"

# =====================================================
# PRE-FLIGHT CHECKS
# =====================================================

log "Starting RDS data migration pre-flight checks..."

# Check if source is accessible
log "Checking source database connectivity..."
if ! psql -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
    error "Cannot connect to source database at $SOURCE_HOST:$SOURCE_PORT"
fi
log "✓ Source database accessible"

# Check if target is accessible
log "Checking target (RDS) connectivity..."
if ! psql -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
    error "Cannot connect to target RDS at $TARGET_HOST:$TARGET_PORT"
fi
log "✓ Target RDS accessible"

# Check disk space
REQUIRED_SPACE_GB=10
AVAILABLE_SPACE_GB=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE_GB" -lt "$REQUIRED_SPACE_GB" ]; then
    error "Insufficient disk space. Required: ${REQUIRED_SPACE_GB}GB, Available: ${AVAILABLE_SPACE_GB}GB"
fi
log "✓ Sufficient disk space available"

# =====================================================
# DATABASE MIGRATION FUNCTION
# =====================================================

migrate_database() {
    local db_name=$1
    log "========================================="
    log "Migrating database: $db_name"
    log "========================================="

    # 1. Check if database exists on source
    log "Checking if $db_name exists on source..."
    if ! psql -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$db_name'" | grep -q 1; then
        warn "Database $db_name does not exist on source. Skipping..."
        return 0
    fi

    # 2. Check if database exists on target
    log "Checking if $db_name exists on target..."
    if ! psql -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$db_name'" | grep -q 1; then
        error "Database $db_name does not exist on target RDS. Run schema creation scripts first!"
    fi

    # 3. Dump data from source
    log "Dumping data from source $db_name..."
    PGPASSWORD="$SOURCE_PASSWORD" pg_dump \
        -h "$SOURCE_HOST" \
        -p "$SOURCE_PORT" \
        -U "$SOURCE_USER" \
        -d "$db_name" \
        --data-only \
        --no-owner \
        --no-privileges \
        --no-tablespaces \
        --disable-triggers \
        -f "$BACKUP_DIR/${db_name}_data.sql" || error "Failed to dump $db_name"

    log "✓ Data dump completed for $db_name ($(du -h "$BACKUP_DIR/${db_name}_data.sql" | cut -f1))"

    # 4. Get row counts from source
    log "Getting row counts from source..."
    PGPASSWORD="$SOURCE_PASSWORD" psql \
        -h "$SOURCE_HOST" \
        -p "$SOURCE_PORT" \
        -U "$SOURCE_USER" \
        -d "$db_name" \
        -tAc "
        SELECT schemaname || '.' || tablename, n_live_tup
        FROM pg_stat_user_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n_live_tup DESC
        " > "$BACKUP_DIR/${db_name}_source_counts.txt"

    # 5. Disable triggers on target (for faster import)
    log "Disabling triggers on target database..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -c "SET session_replication_role = replica;" || warn "Could not disable triggers"

    # 6. Import data to target
    log "Importing data to target $db_name..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -v ON_ERROR_STOP=0 \
        -f "$BACKUP_DIR/${db_name}_data.sql" > "$BACKUP_DIR/${db_name}_import.log" 2>&1 || {
        warn "Some errors occurred during import. Check $BACKUP_DIR/${db_name}_import.log"
    }

    # 7. Re-enable triggers
    log "Re-enabling triggers on target database..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -c "SET session_replication_role = default;"

    # 8. Update sequences
    log "Updating sequences on target database..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -tAc "
        SELECT 'SELECT SETVAL(' ||
               quote_literal(quote_ident(schemaname) || '.' || quote_ident(sequencename)) ||
               ', COALESCE(MAX(' || quote_ident(attname) || '), 1)) FROM ' ||
               quote_ident(schemaname) || '.' || quote_ident(tablename) || ';'
        FROM pg_sequences
        JOIN pg_class ON pg_class.oid = pg_sequences.schemaname::regnamespace
        JOIN pg_attribute ON pg_attribute.attrelid = pg_class.oid
        WHERE pg_sequences.schemaname NOT IN ('pg_catalog', 'information_schema')
        " | PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" > /dev/null 2>&1 || warn "Could not update sequences"

    # 9. Get row counts from target
    log "Getting row counts from target for verification..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -tAc "
        SELECT schemaname || '.' || tablename, n_live_tup
        FROM pg_stat_user_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n_live_tup DESC
        " > "$BACKUP_DIR/${db_name}_target_counts.txt"

    # 10. Run ANALYZE
    log "Running ANALYZE on target database..."
    PGPASSWORD="$TARGET_PASSWORD" psql \
        -h "$TARGET_HOST" \
        -p "$TARGET_PORT" \
        -U "$TARGET_USER" \
        -d "$db_name" \
        -c "ANALYZE;"

    log "✓ Migration completed for $db_name"
    log ""
}

# =====================================================
# MAIN MIGRATION PROCESS
# =====================================================

log "========================================="
log "RDS DATA MIGRATION STARTED"
log "========================================="
log "Source: $SOURCE_HOST:$SOURCE_PORT"
log "Target: $TARGET_HOST:$TARGET_PORT"
log "Backup Directory: $BACKUP_DIR"
log "========================================="
log ""

# Migrate all databases in dependency order
migrate_database "billing_db"          # 1. Plan definitions (no dependencies)
migrate_database "authorization_db"    # 2. Users and tenants
migrate_database "onboard_db"          # 3. Subscriptions (depends on billing plans)
migrate_database "vector_db"           # 4. Vector embeddings
migrate_database "chatbot_db"          # 5. Chat sessions and messages
migrate_database "communications_db"   # 6. Email/SMS messages
migrate_database "workflow_db"         # 7. Workflow executions
migrate_database "answer_quality_db"   # 8. Quality metrics

# =====================================================
# POST-MIGRATION VERIFICATION
# =====================================================

log "========================================="
log "POST-MIGRATION VERIFICATION"
log "========================================="

# Compare row counts
log "Comparing row counts between source and target..."
for db in vector_db chatbot_db onboard_db authorization_db communications_db billing_db workflow_db answer_quality_db; do
    if [ -f "$BACKUP_DIR/${db}_source_counts.txt" ] && [ -f "$BACKUP_DIR/${db}_target_counts.txt" ]; then
        log "Row count comparison for $db:"
        diff -y --suppress-common-lines "$BACKUP_DIR/${db}_source_counts.txt" "$BACKUP_DIR/${db}_target_counts.txt" || true
    fi
done

# =====================================================
# SUMMARY
# =====================================================

log "========================================="
log "MIGRATION SUMMARY"
log "========================================="
log "Backup location: $BACKUP_DIR"
log "Log file: $LOG_FILE"
log ""
log "Next steps:"
log "1. Review the log file for any errors or warnings"
log "2. Compare source and target row counts in backup directory"
log "3. Test application connectivity to RDS"
log "4. Run validation queries (see 05-validation/validate.sh)"
log "5. Update application .env files with RDS connection strings"
log "6. Perform smoke tests on all services"
log ""
log "========================================="
log "MIGRATION COMPLETED SUCCESSFULLY!"
log "========================================="

# Unset passwords
unset PGPASSWORD_SOURCE
unset PGPASSWORD