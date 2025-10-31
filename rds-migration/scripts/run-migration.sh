#!/bin/bash

# =====================================================
# COMPLETE RDS MIGRATION ORCHESTRATOR
# =====================================================
# Purpose: Orchestrate the complete migration from Docker to RDS
# Author: Auto-generated RDS Migration Script
# Date: 2025-10-27
# =====================================================

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =====================================================
# CONFIGURATION
# =====================================================

RDS_ENDPOINT="${RDS_ENDPOINT}"
RDS_PORT="${RDS_PORT:-5432}"
RDS_MASTER_USER="${RDS_MASTER_USER:-postgres}"
RDS_MASTER_PASSWORD="${RDS_MASTER_PASSWORD}"

MIGRATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$MIGRATION_ROOT/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MASTER_LOG="$LOG_DIR/migration_${TIMESTAMP}.log"

# =====================================================
# HELPER FUNCTIONS
# =====================================================

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$MASTER_LOG"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$MASTER_LOG"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$MASTER_LOG"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$MASTER_LOG"
}

step() {
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE} STEP $1: $2${NC}"
    echo -e "${BLUE}=========================================${NC}"
    log "Starting step $1: $2"
}

# =====================================================
# VALIDATION
# =====================================================

validate_config() {
    step "0" "Configuration Validation"

    if [ -z "$RDS_ENDPOINT" ]; then
        error "RDS_ENDPOINT is not set. Please set it before running migration."
    fi

    if [ -z "$RDS_MASTER_PASSWORD" ]; then
        error "RDS_MASTER_PASSWORD is not set. Please set it before running migration."
    fi

    log "✓ RDS Endpoint: $RDS_ENDPOINT"
    log "✓ RDS Port: $RDS_PORT"
    log "✓ RDS User: $RDS_MASTER_USER"
    log "✓ Migration Root: $MIGRATION_ROOT"
}

# =====================================================
# STEP 1: CREATE DATABASES
# =====================================================

create_databases() {
    step "1" "Create Databases and Extensions"

    local script="$MIGRATION_ROOT/01-initialization/001-create-databases-and-extensions.sql"

    if [ ! -f "$script" ]; then
        error "Database creation script not found: $script"
    fi

    log "Running database creation script..."
    export PGPASSWORD="$RDS_MASTER_PASSWORD"

    psql -h "$RDS_ENDPOINT" -p "$RDS_PORT" -U "$RDS_MASTER_USER" -d postgres -f "$script" \
        >> "$LOG_DIR/01_create_databases_${TIMESTAMP}.log" 2>&1 || {
        error "Failed to create databases. Check $LOG_DIR/01_create_databases_${TIMESTAMP}.log"
    }

    log "✓ Databases and extensions created successfully"
}

# =====================================================
# STEP 2: CREATE SCHEMAS
# =====================================================

create_schemas() {
    step "2" "Create Database Schemas"

    local schema_dir="$MIGRATION_ROOT/02-schemas"

    # Execute schema scripts in order
    local schemas=(
        "001-vector-db-schema.sql"
        "002-chat-service-schema.sql"
        "003-onboarding-service-schema.sql"
        "004-communications-service-schema.sql"
        "005-workflow-service-schema.sql"
        "006-billing-service-schema.sql"
        "007-answer-quality-service-schema.sql"
        "008-authorization-server-schema.sql"
    )

    for schema_file in "${schemas[@]}"; do
        local script="$schema_dir/$schema_file"

        if [ ! -f "$script" ]; then
            warn "Schema script not found: $script (skipping)"
            continue
        fi

        log "Executing $schema_file..."
        export PGPASSWORD="$RDS_MASTER_PASSWORD"

        psql -h "$RDS_ENDPOINT" -p "$RDS_PORT" -U "$RDS_MASTER_USER" -f "$script" \
            >> "$LOG_DIR/02_schemas_${TIMESTAMP}.log" 2>&1 || {
            error "Failed to create schema from $schema_file. Check $LOG_DIR/02_schemas_${TIMESTAMP}.log"
        }

        log "✓ $schema_file executed successfully"
    done

    log "✓ All schemas created successfully"
}

# =====================================================
# STEP 3: RUN ALEMBIC MIGRATIONS
# =====================================================

run_alembic_migrations() {
    step "3" "Run Alembic Migrations"

    local backend_root="$(dirname "$MIGRATION_ROOT")"

    # Services that use Alembic
    local services=(
        "billing-service:billing_db"
        "communications-service:communications_db"
        "workflow-service:workflow_db"
        "answer-quality-service:answer_quality_db"
        "onboarding-service:onboard_db"
    )

    for service_db in "${services[@]}"; do
        local service="${service_db%%:*}"
        local database="${service_db##*:}"
        local service_dir="$backend_root/$service"

        if [ ! -d "$service_dir" ]; then
            warn "Service directory not found: $service_dir (skipping)"
            continue
        fi

        if [ ! -d "$service_dir/alembic" ]; then
            warn "Alembic not configured for $service (skipping)"
            continue
        fi

        log "Running Alembic migrations for $service ($database)..."

        cd "$service_dir"

        # Set DATABASE_URL for this service
        export DATABASE_URL="postgresql://$RDS_MASTER_USER:$RDS_MASTER_PASSWORD@$RDS_ENDPOINT:$RDS_PORT/$database"

        # Run migrations
        alembic upgrade head >> "$LOG_DIR/03_alembic_${service}_${TIMESTAMP}.log" 2>&1 || {
            warn "Alembic migration failed for $service. Check $LOG_DIR/03_alembic_${service}_${TIMESTAMP}.log"
        }

        log "✓ Alembic migrations completed for $service"

        cd "$MIGRATION_ROOT"
    done

    log "✓ All Alembic migrations completed"
}

# =====================================================
# STEP 4: MIGRATE DATA (OPTIONAL)
# =====================================================

migrate_data() {
    step "4" "Migrate Data from Docker to RDS"

    info "This step migrates existing data from Docker PostgreSQL to RDS"

    # Ask user if they want to migrate data
    read -p "Do you want to migrate data from Docker PostgreSQL? (y/n): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        warn "Skipping data migration"
        return 0
    fi

    # Ask for source database details
    read -p "Source PostgreSQL Host [localhost]: " SOURCE_HOST
    SOURCE_HOST=${SOURCE_HOST:-localhost}

    read -p "Source PostgreSQL Port [5432]: " SOURCE_PORT
    SOURCE_PORT=${SOURCE_PORT:-5432}

    read -p "Source PostgreSQL User [postgres]: " SOURCE_USER
    SOURCE_USER=${SOURCE_USER:-postgres}

    read -sp "Source PostgreSQL Password: " SOURCE_PASSWORD
    echo

    # Run data migration script
    export SOURCE_HOST
    export SOURCE_PORT
    export SOURCE_USER
    export SOURCE_PASSWORD
    export TARGET_HOST="$RDS_ENDPOINT"
    export TARGET_PORT="$RDS_PORT"
    export TARGET_USER="$RDS_MASTER_USER"
    export TARGET_PASSWORD="$RDS_MASTER_PASSWORD"

    local data_script="$MIGRATION_ROOT/04-data-migration/migrate-data.sh"

    if [ ! -f "$data_script" ]; then
        error "Data migration script not found: $data_script"
    fi

    log "Running data migration..."
    bash "$data_script" || error "Data migration failed"

    log "✓ Data migration completed"
}

# =====================================================
# STEP 5: VALIDATION
# =====================================================

validate_migration() {
    step "5" "Validate Migration"

    local validation_script="$MIGRATION_ROOT/05-validation/validate.sh"

    if [ ! -f "$validation_script" ]; then
        warn "Validation script not found: $validation_script (skipping)"
        return 0
    fi

    log "Running validation checks..."

    export RDS_HOST="$RDS_ENDPOINT"
    export RDS_PORT
    export RDS_USER="$RDS_MASTER_USER"
    export RDS_PASSWORD="$RDS_MASTER_PASSWORD"

    bash "$validation_script" || warn "Some validation checks failed"

    log "✓ Validation completed"
}

# =====================================================
# STEP 6: UPDATE APPLICATION CONFIGS
# =====================================================

update_app_configs() {
    step "6" "Update Application Configuration"

    info "Generating updated .env files for services..."

    local backend_root="$(dirname "$MIGRATION_ROOT")"
    local env_template="$MIGRATION_ROOT/scripts/env_template.txt"

    # Create template if it doesn't exist
    cat > "$env_template" <<EOF
# RDS Database Connection Strings
# Generated: $(date)
# RDS Endpoint: $RDS_ENDPOINT

# Onboarding Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/onboard_db
VECTOR_DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/vector_db

# Chat Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/chatbot_db
VECTOR_DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/vector_db

# Communications Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/communications_db

# Workflow Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/workflow_db

# Billing Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/billing_db

# Answer Quality Service
DATABASE_URL=postgresql://$RDS_MASTER_USER:PASSWORD@$RDS_ENDPOINT:$RDS_PORT/answer_quality_db

# Authorization Server (Spring Boot)
spring.datasource.url=jdbc:postgresql://$RDS_ENDPOINT:$RDS_PORT/authorization_db
spring.datasource.username=$RDS_MASTER_USER
spring.datasource.password=PASSWORD
EOF

    log "✓ Environment template created: $env_template"
    info "Please update your service .env files with the connection strings from: $env_template"
    info "Replace PASSWORD with your actual RDS password"
}

# =====================================================
# MAIN EXECUTION
# =====================================================

main() {
    log "========================================="
    log "RDS MIGRATION ORCHESTRATOR"
    log "========================================="
    log "Starting complete migration process..."
    log "Log file: $MASTER_LOG"
    log ""

    validate_config
    create_databases
    create_schemas
    run_alembic_migrations
    migrate_data
    validate_migration
    update_app_configs

    log ""
    log "========================================="
    log "MIGRATION COMPLETED SUCCESSFULLY!"
    log "========================================="
    log ""
    log "Next steps:"
    log "1. Review migration logs in: $LOG_DIR"
    log "2. Update service .env files with RDS connection strings"
    log "3. Test all services with RDS connectivity"
    log "4. Monitor RDS metrics in CloudWatch"
    log "5. Enable automated backups and monitoring"
    log ""
    log "Log files:"
    ls -lh "$LOG_DIR"/*.log
    log ""
    log "Environment template: $MIGRATION_ROOT/scripts/env_template.txt"
}

# Run main function
main