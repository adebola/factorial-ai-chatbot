# Phase 4 Testing Guide

Complete guide for testing Admin Dashboard, Knowledge Gap Detection, and CSV Export features.

## Prerequisites

1. **Service Running**: Answer-quality-service on port 8005
2. **Database**: PostgreSQL with migrations applied
3. **RabbitMQ**: Running and configured
4. **Test Data**: Some chat messages with quality metrics (from Phase 3 testing)
5. **Admin User**: User with admin role for testing admin endpoints

## Getting Admin Access Token

For testing admin endpoints, you need a JWT token with admin role:

```bash
# Get access token from authorization server
curl -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=webclient" \
  -d "client_secret=webclient-secret"

# Extract the access_token from response
export TOKEN="your-access-token-here"
```

## Access Control Tiers

Admin endpoints are divided into two access tiers:

### Tier 1: Analytics Endpoints (Authenticated Users)

These endpoints are accessible to **any authenticated user** with a valid JWT token. Users can view analytics for their own organization, with automatic tenant isolation ensuring they only see their own data.

**Endpoints**:
- `GET /api/v1/admin/dashboard/overview` - View dashboard statistics
- `GET /api/v1/admin/dashboard/trends` - View quality trends over time
- `GET /api/v1/admin/gaps` - List knowledge gaps (read-only)

**Testing**: Use any valid JWT token from your authorization server.

### Tier 2: Management Endpoints (Admin Role Required)

These endpoints require **admin role** and are restricted because they:
- Perform computationally expensive operations (gap detection)
- Modify data (acknowledge/resolve gaps)
- Export bulk data (CSV reports)

**Endpoints**:
- `POST /api/v1/admin/gaps/detect` - Trigger gap detection (expensive TF-IDF clustering)
- `PATCH /api/v1/admin/gaps/{id}/acknowledge` - Acknowledge a gap
- `PATCH /api/v1/admin/gaps/{id}/resolve` - Resolve a gap
- `GET /api/v1/admin/export/quality-report` - Export CSV report (bulk data)

**Testing**: Requires JWT token with admin role claim.

### Testing Both Tiers

To test both tiers, you'll need tokens for both user types:

```bash
# Regular user token (for Tier 1 analytics endpoints)
curl -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=regular_user" \
  -d "password=password" \
  -d "client_id=webclient" \
  -d "client_secret=webclient-secret"

export REGULAR_TOKEN="regular-user-access-token"

# Admin user token (for Tier 2 management endpoints)
curl -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=webclient" \
  -d "client_secret=webclient-secret"

export ADMIN_TOKEN="admin-user-access-token"
```

## Feature Testing

### 1. Admin Dashboard Overview

**Endpoint**: `GET /api/v1/admin/dashboard/overview`

**Access Level**: **Tier 1 - Authenticated Users** (works with any valid token)

**Purpose**: Get high-level statistics for the admin dashboard.

**Test**:
```bash
# Get overview for last 7 days (default) - works with regular user token
curl http://localhost:8005/api/v1/admin/dashboard/overview \
  -H "Authorization: Bearer $REGULAR_TOKEN"

# Get overview for last 30 days
curl "http://localhost:8005/api/v1/admin/dashboard/overview?days=30" \
  -H "Authorization: Bearer $REGULAR_TOKEN"
```

**Expected Response**:
```json
{
  "period": {
    "days": 7,
    "start_date": "2025-10-11T...",
    "end_date": "2025-10-18T..."
  },
  "metrics": {
    "total_messages": 45,
    "avg_confidence": 0.723,
    "avg_retrieval_score": 0.812,
    "avg_response_time_ms": 1245,
    "low_quality_count": 8,
    "low_quality_percentage": 17.8
  },
  "feedback": {
    "helpful": 32,
    "not_helpful": 5,
    "total": 37,
    "helpful_percentage": 86.5
  },
  "knowledge_gaps": {
    "active_gaps": 3
  }
}
```

**What to verify**:
- ✅ Metrics reflect your actual data
- ✅ Percentages are calculated correctly
- ✅ Different `days` parameter changes the results

---

### 2. Quality Trends Over Time

**Endpoint**: `GET /api/v1/admin/dashboard/trends`

**Access Level**: **Tier 1 - Authenticated Users** (works with any valid token)

**Purpose**: Get daily quality metrics trends.

**Test**:
```bash
# Get trends for last 30 days - works with regular user token
curl "http://localhost:8005/api/v1/admin/dashboard/trends?days=30" \
  -H "Authorization: Bearer $REGULAR_TOKEN"
```

**Expected Response**:
```json
{
  "period": {
    "days": 30,
    "start_date": "2025-09-18T...",
    "end_date": "2025-10-18T..."
  },
  "trends": [
    {
      "date": "2025-10-15",
      "message_count": 12,
      "avg_confidence": 0.745,
      "avg_retrieval": 0.823,
      "feedback": {
        "helpful": 8,
        "not_helpful": 1
      }
    },
    {
      "date": "2025-10-16",
      "message_count": 15,
      "avg_confidence": 0.689,
      "avg_retrieval": 0.791,
      "feedback": {
        "helpful": 10,
        "not_helpful": 2
      }
    }
  ]
}
```

**What to verify**:
- ✅ Each day has aggregated statistics
- ✅ Trends show progression over time
- ✅ Can visualize quality improvement/degradation

---

### 3. Knowledge Gap Detection

**Endpoint**: `POST /api/v1/admin/gaps/detect`

**Access Level**: **Tier 2 - Admin Role Required** (computationally expensive operation)

**Purpose**: Manually trigger gap detection to find recurring low-quality questions.

**Test**:
```bash
# Trigger gap detection for last 7 days - requires admin token
curl -X POST "http://localhost:8005/api/v1/admin/gaps/detect?days=7" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected Response**:
```json
{
  "success": true,
  "gaps_detected": 2,
  "gaps": [
    {
      "id": "uuid-1",
      "question_pattern": "How do I reset my password?",
      "occurrence_count": 5,
      "status": "detected"
    },
    {
      "id": "uuid-2",
      "question_pattern": "What are your business hours?",
      "occurrence_count": 3,
      "status": "detected"
    }
  ]
}
```

**What to verify**:
- ✅ Similar questions are clustered together
- ✅ Gaps with low confidence/negative feedback are detected
- ✅ `occurrence_count` reflects how many times the pattern appeared

**How it works**:
1. Fetches messages with low confidence (<0.5) or negative feedback
2. Uses TF-IDF vectorization to analyze question text
3. Groups similar questions using cosine similarity (threshold: 0.7)
4. Creates knowledge gap records for recurring patterns

---

### 4. List Knowledge Gaps

**Endpoint**: `GET /api/v1/admin/gaps`

**Access Level**: **Tier 1 - Authenticated Users** (read-only access)

**Purpose**: View all detected knowledge gaps.

**Test**:
```bash
# List all gaps - works with regular user token
curl http://localhost:8005/api/v1/admin/gaps \
  -H "Authorization: Bearer $REGULAR_TOKEN"

# List only detected gaps
curl "http://localhost:8005/api/v1/admin/gaps?status=detected" \
  -H "Authorization: Bearer $REGULAR_TOKEN"

# List resolved gaps
curl "http://localhost:8005/api/v1/admin/gaps?status=resolved" \
  -H "Authorization: Bearer $REGULAR_TOKEN"

# Limit results
curl "http://localhost:8005/api/v1/admin/gaps?limit=10" \
  -H "Authorization: Bearer $REGULAR_TOKEN"
```

**Expected Response**:
```json
{
  "count": 2,
  "gaps": [
    {
      "id": "uuid-1",
      "question_pattern": "How do I reset my password?",
      "example_questions": [
        "How do I reset my password?",
        "I forgot my password, how can I reset it?",
        "Password reset procedure?"
      ],
      "occurrence_count": 5,
      "avg_confidence": 0.42,
      "negative_feedback_count": 3,
      "status": "detected",
      "first_detected_at": "2025-10-15T10:30:00",
      "last_occurrence_at": "2025-10-18T14:22:00",
      "resolved_at": null,
      "resolution_notes": null
    }
  ]
}
```

**What to verify**:
- ✅ Gaps are sorted by occurrence count (most frequent first)
- ✅ Example questions show actual user queries
- ✅ Status filtering works correctly

---

### 5. Acknowledge Knowledge Gap

**Endpoint**: `PATCH /api/v1/admin/gaps/{gap_id}/acknowledge`

**Access Level**: **Tier 2 - Admin Role Required** (modifies data)

**Purpose**: Mark a gap as "acknowledged" (admin is aware of it).

**Test**:
```bash
# Acknowledge a gap with optional notes - requires admin token
curl -X PATCH http://localhost:8005/api/v1/admin/gaps/{gap_id}/acknowledge \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "notes": "Working on adding password reset documentation"
  }'
```

**Expected Response**:
```json
{
  "success": true,
  "gap_id": "uuid-1",
  "status": "acknowledged"
}
```

**What to verify**:
- ✅ Gap status changes from "detected" to "acknowledged"
- ✅ Notes are stored (optional)
- ✅ Gap no longer appears in detected-only queries

---

### 6. Resolve Knowledge Gap

**Endpoint**: `PATCH /api/v1/admin/gaps/{gap_id}/resolve`

**Access Level**: **Tier 2 - Admin Role Required** (modifies data)

**Purpose**: Mark a gap as "resolved" (issue has been fixed).

**Test**:
```bash
# Resolve a gap with resolution notes (required) - requires admin token
curl -X PATCH http://localhost:8005/api/v1/admin/gaps/{gap_id}/resolve \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution_notes": "Added comprehensive password reset documentation to knowledge base"
  }'
```

**Expected Response**:
```json
{
  "success": true,
  "gap_id": "uuid-1",
  "status": "resolved"
}
```

**What to verify**:
- ✅ Gap status changes to "resolved"
- ✅ `resolved_at` timestamp is set
- ✅ `resolution_notes` are saved
- ✅ Gap no longer appears in active gaps count

---

### 7. Export Quality Report (CSV)

**Endpoint**: `GET /api/v1/admin/export/quality-report`

**Access Level**: **Tier 2 - Admin Role Required** (bulk data export)

**Purpose**: Download CSV file with detailed quality metrics.

**Test**:
```bash
# Export last 30 days as CSV - requires admin token
curl "http://localhost:8005/api/v1/admin/export/quality-report?days=30&format=csv" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -o quality-report.csv

# View the file
cat quality-report.csv
```

**Expected CSV Format**:
```csv
Message ID,Session ID,Created At,Confidence Score,Retrieval Score,Documents Retrieved,Response Time (ms),Sentiment,Feedback Type,Feedback Comment,Quality Issues
uuid-msg-1,uuid-session-1,2025-10-18T10:30:00,0.42,0.65,3,1245,negative,not_helpful,Not helpful at all,Low Confidence
uuid-msg-2,uuid-session-1,2025-10-18T10:35:00,0.89,0.92,5,980,positive,helpful,,
uuid-msg-3,uuid-session-2,2025-10-18T11:00:00,0.35,0.28,1,3420,neutral,not_helpful,,Low Confidence; Poor Retrieval; Slow Response
```

**What to verify**:
- ✅ CSV file downloads successfully
- ✅ Headers are correct
- ✅ Data includes quality metrics and feedback
- ✅ Quality issues are flagged correctly
- ✅ Can open in Excel/Google Sheets for analysis

---

## Complete Testing Workflow

Here's a complete workflow to test all Phase 4 features:

### Step 1: Create Test Data (if needed)

If you don't have enough test data, generate some low-quality responses:

```bash
# Send several chat messages that might have low quality
# (questions that don't match your knowledge base well)
```

### Step 2: Check Initial Dashboard

```bash
# Get overview
curl http://localhost:8005/api/v1/admin/dashboard/overview \
  -H "Authorization: Bearer $TOKEN"

# Save the numbers for comparison
```

### Step 3: Trigger Gap Detection

```bash
# Detect gaps
curl -X POST "http://localhost:8005/api/v1/admin/gaps/detect?days=7" \
  -H "Authorization: Bearer $TOKEN"

# Should return detected gaps
```

### Step 4: Review Gaps

```bash
# List all gaps
curl "http://localhost:8005/api/v1/admin/gaps?status=detected" \
  -H "Authorization: Bearer $TOKEN" | jq

# Copy a gap_id from the response
```

### Step 5: Manage Gaps

```bash
# Acknowledge a gap
curl -X PATCH http://localhost:8005/api/v1/admin/gaps/{gap_id}/acknowledge \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Investigating this issue"}'

# Verify status changed
curl "http://localhost:8005/api/v1/admin/gaps?status=acknowledged" \
  -H "Authorization: Bearer $TOKEN"

# Resolve the gap
curl -X PATCH http://localhost:8005/api/v1/admin/gaps/{gap_id}/resolve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes": "Fixed by adding new documentation"}'
```

### Step 6: View Trends

```bash
# Get trends
curl "http://localhost:8005/api/v1/admin/dashboard/trends?days=7" \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Step 7: Export Report

```bash
# Download CSV
curl "http://localhost:8005/api/v1/admin/export/quality-report?days=30" \
  -H "Authorization: Bearer $TOKEN" \
  -o quality-report.csv

# Open in Excel
open quality-report.csv
```

---

## Database Verification

You can also verify the data directly in the database:

```sql
-- View knowledge gaps
SELECT id, question_pattern, occurrence_count, status, avg_confidence
FROM knowledge_gaps
WHERE tenant_id = 'your-tenant-id'
ORDER BY occurrence_count DESC;

-- View low-quality messages
SELECT message_id, answer_confidence, retrieval_score, sentiment_label
FROM rag_quality_metrics
WHERE tenant_id = 'your-tenant-id'
  AND answer_confidence < 0.5
ORDER BY created_at DESC
LIMIT 10;

-- View feedback statistics
SELECT feedback_type, COUNT(*) as count
FROM answer_feedback
WHERE tenant_id = 'your-tenant-id'
GROUP BY feedback_type;
```

---

## Troubleshooting

### No gaps detected

**Possible causes**:
- Not enough low-quality messages in the time period
- Confidence threshold too strict (default: <0.5)
- No negative feedback received
- Questions are too diverse (can't cluster)

**Solutions**:
- Increase `days` parameter
- Send more test messages with questions outside your knowledge base
- Manually give some messages negative feedback

### CSV export is empty

**Possible causes**:
- No data in the time period
- User not authenticated properly

**Solutions**:
- Check the time range with dashboard overview first
- Verify admin token is valid

### Authentication errors

**Possible causes**:
- Token expired
- User doesn't have admin role
- Authorization server not running

**Solutions**:
- Get a fresh token
- Verify user has admin role in database
- Check authorization server is running on port 9002

---

## Success Criteria

Phase 4 is successfully implemented when:

- ✅ Dashboard shows accurate metrics and statistics
- ✅ Trends display daily aggregated quality data
- ✅ Gap detection clusters similar low-quality questions
- ✅ Gaps can be acknowledged and resolved
- ✅ CSV export includes all quality metrics and feedback
- ✅ **Tier 1 endpoints** (dashboard, trends, gap listing) work with regular user tokens
- ✅ **Tier 2 endpoints** (gap detection, modifications, exports) require admin role
- ✅ Tenant isolation ensures users only see their own organization's data
- ✅ Logs show gap detection activity with tenant context

---

## Next Steps

After Phase 4 testing:

1. **Schedule Gap Detection**: Set up a cron job or scheduler to run gap detection daily
2. **Alerts**: Add alerting when quality drops below thresholds
3. **Visualization**: Build a frontend dashboard using these APIs
4. **Advanced Analytics**: Add more sophisticated ML-based gap detection
5. **Integration**: Connect gap resolution to document ingestion workflow
