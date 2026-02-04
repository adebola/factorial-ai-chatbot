#!/bin/bash

# Script to rebuild the superadmin frontend with logout fix

echo "=========================================="
echo "REBUILDING SUPERADMIN FRONTEND"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Navigate to frontend directory
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/frontend/chatcraft-superadmin

print_info "Current directory: $(pwd)"
echo ""

# Check if process is running on port 4201
print_info "Checking for running processes on port 4201..."
PIDS=$(lsof -ti:4201 || echo "")

if [ ! -z "$PIDS" ]; then
    print_info "Found running processes: $PIDS"
    echo "Stopping Angular dev server..."
    kill -9 $PIDS 2>/dev/null || true
    sleep 2
    print_success "Stopped running processes"
else
    print_info "No processes running on port 4201"
fi
echo ""

# Verify the fix is in place
print_info "Verifying logout fix is present..."
if grep -q "Create Basic Authentication credentials (required by OAuth2 revocation endpoint)" src/app/core/services/auth.service.ts; then
    print_success "Logout fix is present in source code"
else
    echo "❌ ERROR: Logout fix not found in source code!"
    exit 1
fi
echo ""

# Install dependencies (if needed)
print_info "Installing dependencies (if needed)..."
npm install --silent
print_success "Dependencies ready"
echo ""

# Start dev server
print_info "Starting Angular dev server..."
print_info "The application will be available at http://localhost:4201"
print_info "Press Ctrl+C to stop the server when testing is complete"
echo ""

npm start

# Note: This will keep running until Ctrl+C
