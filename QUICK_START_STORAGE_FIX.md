# Quick Start: Testing Storage Statistics Fix

## TL;DR - Run This First

```bash
# Navigate to backend directory
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend

# Run automated verification test
./test-storage-statistics-fix.sh
```

This will:
1. ✅ Upload test files with known sizes
2. ✅ Verify `file_size` is populated in database
3. ✅ Verify `storage_used_mb` shows accurate values
4. ✅ Run comprehensive validation tests

Expected output: **ALL TESTS PASSED!** ✅

---

## What Was Fixed

**Problem**: `storage_used_mb` always returned 0.0 MB

**Root Cause**: `Document.file_size` was never populated during upload

**Solution**:
- Capture file size from `UploadFile.size`
- Store it in database during document creation
- Calculate accurate storage statistics

---

## Files Changed

### Modified (3 files)
1. `onboarding-service/app/api/documents.py` - Capture file_size
2. `onboarding-service/app/services/document_processor.py` - Store file_size
3. `onboarding-service/app/api/admin_stats.py` - Fix query logic

### Created (3 files)
1. `test-storage-statistics-fix.sh` - Automated test script
2. `backfill_document_file_sizes.py` - Optional backfill for existing docs
3. `STORAGE_STATISTICS_FIX.md` - Detailed documentation

---

## Quick Verification (Manual)

### 1. Check if services are running:
```bash
# Onboarding service (port 8001)
curl http://localhost:8001/health

# Authorization server (port 9002)
curl http://localhost:9002/auth/actuator/health
```

### 2. Get access token:
```bash
TOKEN=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret" | jq -r '.access_token')

TENANT_ID=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret" | jq -r '.tenant_id')

echo "Token: $TOKEN"
echo "Tenant ID: $TENANT_ID"
```

### 3. Upload a test document:
```bash
# Create test file
echo "Test document content" > /tmp/test.txt

# Upload
curl -X POST http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.txt"
```

### 4. Check statistics:
```bash
curl -X GET "http://localhost:8001/api/v1/admin/stats?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.storage_used_mb'
```

**Before fix**: `0.0`
**After fix**: Non-zero value (e.g., `0.02`)

---

## Backfill Existing Documents (Optional)

If you have documents uploaded before this fix:

### 1. Dry run first:
```bash
cd onboarding-service
python backfill_document_file_sizes.py --dry-run
```

### 2. Review output, then run live:
```bash
python backfill_document_file_sizes.py
```

### 3. For specific tenant only:
```bash
python backfill_document_file_sizes.py --tenant-id abc-123
```

---

## Troubleshooting

### Test script fails with "command not found: jq"
```bash
# Install jq (macOS)
brew install jq

# Install jq (Ubuntu/Debian)
apt-get install jq
```

### Test script fails with "command not found: bc"
```bash
# Install bc (macOS)
brew install bc

# Install bc (Ubuntu/Debian)
apt-get install bc
```

### "Failed to obtain access token"
- Check if authorization server is running on port 9002
- Verify credentials in CLAUDE.md are correct
- Check authorization server logs

### "storage_used_mb still shows 0.0"
- Ensure onboarding service restarted after code changes
- Check if file upload succeeded (document_id returned)
- Verify file_size in database is not NULL
- Check application logs for errors

### Database check:
```bash
docker exec -it postgres psql -U chatcraft -d chatcraft -c \
  "SELECT id, filename, file_size, created_at FROM documents ORDER BY created_at DESC LIMIT 5;"
```

**Expected**: `file_size` column shows byte values (not NULL)

---

## Success Indicators

✅ Test script shows "ALL TESTS PASSED!"
✅ `file_size` column in database has values (not NULL)
✅ `storage_used_mb` endpoint returns non-zero values
✅ Storage increases when uploading documents
✅ Admin app shows accurate storage statistics

---

## Next Steps

1. ✅ Run automated test: `./test-storage-statistics-fix.sh`
2. ⚠️ Backfill existing documents (optional): `python backfill_document_file_sizes.py`
3. 📊 Verify in admin app: Check tenant statistics page
4. 🚀 Deploy to production when ready

---

## Support

- Detailed docs: `STORAGE_STATISTICS_FIX.md`
- Test script: `test-storage-statistics-fix.sh`
- Backfill script: `onboarding-service/backfill_document_file_sizes.py`
- Test credentials: See `CLAUDE.md`
