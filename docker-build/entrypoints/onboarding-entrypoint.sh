#!/bin/bash
# ==============================================================================
# Onboarding Service Entrypoint Script
# ==============================================================================
# This script handles the startup of the onboarding service container.
# It optionally installs Playwright + Chromium browser at runtime to reduce
# Docker image size from 2GB to ~600MB.
#
# Environment Variables:
#   INSTALL_PLAYWRIGHT - Set to "true" to install Playwright (default: true)
#                        Set to "false" to skip installation (faster startup,
#                        but JavaScript website scraping will not be available)
#   PLAYWRIGHT_BROWSERS_PATH - Path where Playwright browsers will be stored
#                              (default: /app/.cache/ms-playwright)
# ==============================================================================

set -e  # Exit on error

echo "========================================"
echo "Onboarding Service Starting..."
echo "========================================"

# Set Playwright cache directory (should match Dockerfile ENV)
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/app/.cache/ms-playwright}"

# Ensure the cache directory exists and has proper permissions
if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH" ]; then
    echo "Creating Playwright cache directory: $PLAYWRIGHT_BROWSERS_PATH"
    mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
fi

# Check if we have write permissions
if [ ! -w "$PLAYWRIGHT_BROWSERS_PATH" ]; then
    echo "ERROR: No write permission for $PLAYWRIGHT_BROWSERS_PATH"
    echo "This will prevent Playwright browser installation"
    echo "Continuing anyway - Playwright installation may fail"
fi

# Check if Playwright should be installed
INSTALL_PLAYWRIGHT="${INSTALL_PLAYWRIGHT:-true}"

if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then
    echo "Checking Playwright installation status..."
    echo "Playwright cache directory: $PLAYWRIGHT_BROWSERS_PATH"

    # Smart version detection - check if cached browsers match current Playwright version
    echo "Checking Playwright version compatibility..."

    # Get Playwright library version from pip
    PLAYWRIGHT_VERSION=$(pip show playwright 2>/dev/null | grep "^Version:" | awk '{print $2}')

    if [ -n "$PLAYWRIGHT_VERSION" ]; then
        echo "Playwright library version: $PLAYWRIGHT_VERSION"

        # Try to determine expected browser revision using Playwright CLI
        # This queries Playwright to see what browser version it expects
        EXPECTED_REVISION=$(python3 -c "
import sys
try:
    # Use Playwright's internal mechanism to check browser requirements
    from playwright._impl._driver import compute_driver_executable
    driver_executable, _ = compute_driver_executable()

    # Query the driver for the expected chromium executable path
    import subprocess
    result = subprocess.run(
        [driver_executable, 'print-browser-executable', 'chromium'],
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode == 0 and 'chromium' in result.stdout:
        # Extract revision number from path (e.g., chromium-1200)
        import re
        match = re.search(r'chromium[_-](\d+)', result.stdout)
        if match:
            print(match.group(1))
except Exception:
    # Fallback: don't fail, just skip version check
    pass
" 2>/dev/null)

        if [ -n "$EXPECTED_REVISION" ]; then
            echo "Expected chromium revision: $EXPECTED_REVISION"

            # Check if this specific revision exists in cache
            if ls "$PLAYWRIGHT_BROWSERS_PATH"/chromium*"$EXPECTED_REVISION"* 1> /dev/null 2>&1; then
                echo "✓ Browser version matches Playwright library (chromium-$EXPECTED_REVISION)"
            else
                echo "⚠ Version mismatch detected!"
                echo "Expected: chromium-$EXPECTED_REVISION"
                echo "Cached browsers:"
                ls -1 "$PLAYWRIGHT_BROWSERS_PATH" 2>/dev/null | grep -E "chromium|ffmpeg|firefox|webkit" || echo "  (none)"
                echo "Clearing outdated cache (removing all browser binaries including ffmpeg)..."
                # Remove all Playwright binaries: chromium, firefox, webkit, and ffmpeg
                rm -rf "$PLAYWRIGHT_BROWSERS_PATH/chromium-"*
                rm -rf "$PLAYWRIGHT_BROWSERS_PATH/firefox-"*
                rm -rf "$PLAYWRIGHT_BROWSERS_PATH/webkit-"*
                rm -rf "$PLAYWRIGHT_BROWSERS_PATH/ffmpeg-"*
                echo "Cache cleared - will download correct versions"
            fi
        else
            echo "Could not determine expected browser revision - will rely on standard check"
        fi
    fi

    # Check if Chromium browser is already installed
    # Look for the chromium directory in the cache path
    if [ -d "$PLAYWRIGHT_BROWSERS_PATH/chromium-"* ] 2>/dev/null; then
        echo "✓ Playwright Chromium already installed"
        # List installed browsers for verification
        if command -v playwright &> /dev/null; then
            playwright --version 2>/dev/null || echo "  (Playwright version check skipped)"
        fi
    else
        echo "Installing Playwright Chromium browser..."
        echo "This is a one-time installation (30-60 seconds)"
        echo "Service will be available immediately while installation continues in background"
        echo ""

        # Install Playwright browsers in background
        # This allows the service to start immediately
        # First website scraping request will wait if installation still in progress
        # NOTE: Using 'playwright install chromium' WITHOUT --with-deps flag
        #       because system dependencies are already installed in Dockerfile
        (
            echo "[Playwright Installer] Starting installation at $(date)"
            echo "[Playwright Installer] Cache directory: $PLAYWRIGHT_BROWSERS_PATH"
            echo "[Playwright Installer] User: $(whoami)"
            echo "[Playwright Installer] Permissions: $(ls -ld $PLAYWRIGHT_BROWSERS_PATH 2>/dev/null || echo 'N/A')"

            if playwright install chromium 2>&1 | tee /tmp/playwright-install.log; then
                echo "[Playwright Installer] ✓ Installation complete at $(date)"
                echo "[Playwright Installer] Installed browsers:"
                ls -lh "$PLAYWRIGHT_BROWSERS_PATH/" 2>/dev/null || echo "  (Could not list browsers)"
                rm -f /tmp/playwright-install.log
            else
                echo "[Playwright Installer] ✗ Installation failed at $(date)"
                echo "[Playwright Installer] Last 20 lines of installation log:"
                tail -20 /tmp/playwright-install.log 2>/dev/null || echo "  (No log available)"
                echo "[Playwright Installer] Website scraping with JavaScript will not be available"
                echo "[Playwright Installer] The service will still start, but only requests-based scraping will work"
            fi
        ) &

        # Store background process ID
        PLAYWRIGHT_PID=$!
        echo "Playwright installation running in background (PID: $PLAYWRIGHT_PID)"
        echo "Service will start immediately..."
    fi
elif [ "$INSTALL_PLAYWRIGHT" = "false" ]; then
    echo "INSTALL_PLAYWRIGHT=false - Skipping Playwright installation"
    echo "Note: Website scraping with JavaScript rendering will not be available"
    echo "      Only requests-based scraping will work"
else
    echo "Warning: Invalid INSTALL_PLAYWRIGHT value: '$INSTALL_PLAYWRIGHT'"
    echo "         Expected 'true' or 'false'. Defaulting to 'true'"
    INSTALL_PLAYWRIGHT="true"
fi

echo ""
echo "========================================"
echo "Starting Onboarding Service Application"
echo "========================================"
echo "Service will be available at: http://0.0.0.0:8000"
echo "API documentation: http://0.0.0.0:8000/docs"
echo ""

# Execute the command passed to docker run
# This will be the CMD from Dockerfile (uvicorn command)
exec "$@"
