# Playwright Browser Installation

## Problem

Website ingestions were failing with the error:
```
BrowserType.launch: Executable doesn't exist at /Users/adebola/Library/Caches/ms-playwright/chromium_headless_shell-1187/chrome-mac/headless_shell
```

This error was previously hidden due to missing logging fields, but became visible after the logging fixes.

## Root Cause

Playwright Python package was installed (`playwright>=1.55.0` in requirements.txt), but the actual browser binaries were not downloaded. Playwright requires a separate installation step to download the browser executables.

## Solution Applied

Installed Playwright Chromium browser:

```bash
cd onboarding-service
python -m playwright install chromium
```

### What Was Downloaded

1. **Chromium 140.0.7339.16** (129.7 MB)
   - Location: `/Users/adebola/Library/Caches/ms-playwright/chromium-1187`

2. **Chromium Headless Shell 140.0.7339.16** (81.9 MB)
   - Location: `/Users/adebola/Library/Caches/ms-playwright/chromium_headless_shell-1187`
   - This is what the website scraper actually uses

3. **FFMPEG build v1011** (1 MB)
   - Location: `/Users/adebola/Library/Caches/ms-playwright/ffmpeg-1011`
   - Used for media processing

## Verification

Tested Playwright installation:

```bash
✅ Playwright working! Page title: Example Domain
```

## How to Test Website Ingestion

1. **Start the onboarding service:**
   ```bash
   cd onboarding-service
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```

2. **Try ingesting a website** (e.g., `https://www.abbeymortgagebank.com/`)

3. **Check the logs** - you should now see detailed error messages if anything fails:
   ```
   ✅ Good logs now show:
   - tenant_id
   - url
   - error message
   - full stack trace
   ```

## Why This Happened

1. Playwright Python package is installed via `pip install playwright`
2. But the browser binaries must be installed separately with `playwright install`
3. This is a two-step process that's often missed in documentation
4. The error was not visible in logs until we fixed the logging configuration

## For Future Deployments

When deploying to a new environment (Docker, new server, etc.), remember to:

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install Playwright browsers:
   ```bash
   python -m playwright install chromium
   ```

### Dockerfile Addition

If using Docker, add this to your Dockerfile after installing requirements:

```dockerfile
# Install Python dependencies
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install chromium
```

## Alternative: Install All Browsers

If you need other browsers (Firefox, WebKit) in the future:

```bash
# Install all browsers
python -m playwright install

# Or specific ones
python -m playwright install firefox
python -m playwright install webkit
```

Currently, only Chromium is needed for the website scraping functionality.

## Storage Requirements

- Chromium: ~130 MB
- Chromium Headless Shell: ~82 MB
- FFMPEG: ~1 MB
- **Total:** ~213 MB

Browsers are cached in `/Users/adebola/Library/Caches/ms-playwright/` and shared across all projects using Playwright.

---

**Status:** ✅ Complete
**Impact:** Website ingestion now works without browser errors
**Next Steps:** Test website ingestion through the UI or API
