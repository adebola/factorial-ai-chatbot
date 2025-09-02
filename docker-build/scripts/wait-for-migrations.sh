#!/bin/bash
# Wait for database migrations to complete before starting services
# This script is used internally by Docker Compose

set -e

SERVICE_NAME=${1:-"unknown-service"}
MAX_WAIT=${2:-300}  # 5 minutes default
SLEEP_INTERVAL=5

echo "⏳ [$SERVICE_NAME] Waiting for database migrations to complete..."

wait_count=0
while [ $wait_count -lt $MAX_WAIT ]; do
    # Check if migration containers have completed
    CHAT_MIGRATION_STATUS=$(docker-compose ps -q chat-migration | xargs docker inspect -f '{{.State.ExitCode}}' 2>/dev/null || echo "running")
    ONBOARDING_MIGRATION_STATUS=$(docker-compose ps -q onboarding-migration | xargs docker inspect -f '{{.State.ExitCode}}' 2>/dev/null || echo "running")
    
    if [ "$CHAT_MIGRATION_STATUS" = "0" ] && [ "$ONBOARDING_MIGRATION_STATUS" = "0" ]; then
        echo "✅ [$SERVICE_NAME] All migrations completed successfully!"
        exit 0
    fi
    
    if [ "$CHAT_MIGRATION_STATUS" != "0" ] && [ "$CHAT_MIGRATION_STATUS" != "running" ]; then
        echo "❌ [$SERVICE_NAME] Chat migration failed with exit code: $CHAT_MIGRATION_STATUS"
        exit 1
    fi
    
    if [ "$ONBOARDING_MIGRATION_STATUS" != "0" ] && [ "$ONBOARDING_MIGRATION_STATUS" != "running" ]; then
        echo "❌ [$SERVICE_NAME] Onboarding migration failed with exit code: $ONBOARDING_MIGRATION_STATUS"
        exit 1
    fi
    
    echo "⏳ [$SERVICE_NAME] Still waiting for migrations... (${wait_count}s/${MAX_WAIT}s)"
    sleep $SLEEP_INTERVAL
    wait_count=$((wait_count + SLEEP_INTERVAL))
done

echo "⏰ [$SERVICE_NAME] Timeout waiting for migrations to complete"
exit 1