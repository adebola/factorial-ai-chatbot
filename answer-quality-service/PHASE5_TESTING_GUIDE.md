# Phase 5: Scheduled Jobs & Alerting System - Testing Guide

This guide provides comprehensive testing instructions for Phase 5 features of the Answer Quality & Feedback Service.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Manual Testing](#manual-testing)
5. [Testing Alert Rule Types](#testing-alert-rule-types)
6. [Testing Notification Channels](#testing-notification-channels)
7. [Testing Scheduled Jobs](#testing-scheduled-jobs)
8. [Troubleshooting](#troubleshooting)

---

## Overview

Phase 5 introduces a comprehensive alerting and scheduling system that:

- **Monitors quality metrics** continuously through scheduled jobs
- **Triggers alerts** when quality thresholds are breached
- **Sends notifications** through multiple channels (email, webhook, console)
- **Logs execution history** for all scheduled jobs and alerts
- **Provides admin APIs** for managing alert rules

---

## Prerequisites

### 1. Running Services

Ensure the following services are running:

```bash
# Answer Quality Service
./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8005

# Authorization Server (for JWT tokens)
# Should be running on http://localhost:9002/auth

# Communications Service (for email alerts)
# Should be running on http://localhost:8003
```

### 2. Database Setup

Apply the Phase 5 migration:

```bash
alembic upgrade head
```

Verify tables were created:

```sql
SELECT * FROM alert_rules;
SELECT * FROM alert_history;
SELECT * FROM job_execution_logs;
```

### 3. Dependencies

Install Phase 5 dependencies:

```bash
pip install APScheduler==3.10.4 pytz==2023.3
```

### 4. Test Credentials

Use the following test credentials:

- **Username**: `adebola`
- **Password**: `password`
- **Client ID**: `frontend-client`
- **Client Secret**: `secret`

---

## Quick Start

### Automated Testing

Run the comprehensive test script:

```bash
cd /path/to/answer-quality-service
./test_phase5.sh
```

This script tests all Phase 5 features automatically and provides detailed output.

### Manual Quick Test

```bash
# 1. Get access token
TOKEN=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret" | jq -r '.access_token')

# 2. Check scheduler status
curl -X GET "http://localhost:8005/api/v1/alerts/scheduler/status" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# 3. Send test alert
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channels": ["console"]}' | jq '.'
```

---

## Manual Testing

### 1. Scheduler Status Monitoring

**Endpoint**: `GET /api/v1/alerts/scheduler/status`

**Test**:

```bash
curl -X GET "http://localhost:8005/api/v1/alerts/scheduler/status" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

**Expected Response**:

```json
{
  "scheduler_running": true,
  "job_count": 2,
  "jobs": [
    {
      "id": "gap_detection",
      "name": "Daily Knowledge Gap Detection",
      "next_run_time": "2025-10-21T02:00:00+00:00",
      "trigger": "cron[hour='2']"
    },
    {
      "id": "quality_check",
      "name": "Periodic Quality Alert Check",
      "next_run_time": "2025-10-20T15:00:00+00:00",
      "trigger": "cron[hour='*']"
    }
  ]
}
```

---

### 2. Create Alert Rule

**Endpoint**: `POST /api/v1/alerts/rules`

**Test - Quality Drop Alert**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Low Confidence Alert",
    "rule_type": "quality_drop",
    "description": "Alert when average confidence drops below 0.6",
    "threshold_value": 0.6,
    "check_interval_hours": 1,
    "min_sample_size": 5,
    "notification_channels": ["console", "email"],
    "notification_recipients": {
      "emails": ["admin@example.com"]
    },
    "throttle_minutes": 60,
    "enabled": true
  }' | jq '.'
```

**Expected Response**:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Low Confidence Alert",
  "rule_type": "quality_drop",
  "enabled": true,
  "created_at": "2025-10-20T14:30:00"
}
```

---

### 3. List Alert Rules

**Endpoint**: `GET /api/v1/alerts/rules`

**Test**:

```bash
# List all rules
curl -X GET "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# List only enabled rules
curl -X GET "http://localhost:8005/api/v1/alerts/rules?enabled_only=true" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 4. Get Specific Alert Rule

**Endpoint**: `GET /api/v1/alerts/rules/{rule_id}`

**Test**:

```bash
RULE_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X GET "http://localhost:8005/api/v1/alerts/rules/$RULE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 5. Update Alert Rule

**Endpoint**: `PUT /api/v1/alerts/rules/{rule_id}`

**Test**:

```bash
RULE_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X PUT "http://localhost:8005/api/v1/alerts/rules/$RULE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "threshold_value": 0.65,
    "enabled": false
  }' | jq '.'
```

---

### 6. Delete Alert Rule

**Endpoint**: `DELETE /api/v1/alerts/rules/{rule_id}`

**Test**:

```bash
RULE_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X DELETE "http://localhost:8005/api/v1/alerts/rules/$RULE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 7. View Alert History

**Endpoint**: `GET /api/v1/alerts/history`

**Test**:

```bash
# View all alerts
curl -X GET "http://localhost:8005/api/v1/alerts/history" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Filter by rule
curl -X GET "http://localhost:8005/api/v1/alerts/history?rule_id=RULE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Filter by severity
curl -X GET "http://localhost:8005/api/v1/alerts/history?severity=critical" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 8. Send Test Alert

**Endpoint**: `POST /api/v1/alerts/test`

**Test**:

```bash
# Console notification
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["console"]
  }' | jq '.'

# Email notification
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["email"],
    "recipients": {
      "emails": ["test@example.com"]
    }
  }' | jq '.'
```

---

### 9. Manually Trigger Alert Check

**Endpoint**: `POST /api/v1/alerts/check-now`

**Test**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/check-now" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

**Expected Response**:

```json
{
  "success": true,
  "result": {
    "total_rules_checked": 4,
    "alerts_triggered": 1,
    "results": [...]
  }
}
```

---

### 10. View Job Execution Logs

**Endpoint**: `GET /api/v1/alerts/jobs/logs`

**Test**:

```bash
# View all logs
curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Filter by job type
curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs?job_type=quality_check" \
  -H "Authorization: Bearer $TOKEN" | jq '.'

# Filter by status
curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs?status_filter=failed" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

## Testing Alert Rule Types

### 1. Quality Drop Alert

Tests when average answer confidence falls below a threshold.

**Setup**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Quality Drop Test",
    "rule_type": "quality_drop",
    "threshold_value": 0.7,
    "check_interval_hours": 1,
    "min_sample_size": 3,
    "notification_channels": ["console"],
    "throttle_minutes": 60,
    "enabled": true
  }'
```

**Trigger Alert**: Submit several low-confidence quality metrics, then run manual check.

---

### 2. New Gaps Alert

Tests when new knowledge gaps are detected.

**Setup**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Gaps Test",
    "rule_type": "new_gaps",
    "threshold_value": 2,
    "check_interval_hours": 24,
    "min_sample_size": 1,
    "notification_channels": ["console"],
    "throttle_minutes": 1440,
    "enabled": true
  }'
```

**Trigger Alert**: Use gap detection endpoint to create knowledge gaps.

---

### 3. High Negative Feedback Alert

Tests when negative feedback rate exceeds threshold.

**Setup**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Negative Feedback Test",
    "rule_type": "high_negative_feedback",
    "threshold_value": 0.3,
    "check_interval_hours": 6,
    "min_sample_size": 5,
    "notification_channels": ["console"],
    "throttle_minutes": 360,
    "enabled": true
  }'
```

**Trigger Alert**: Submit several "not_helpful" feedback entries.

---

### 4. Session Degradation Alert

Tests when multiple sessions have poor quality.

**Setup**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Session Degradation Test",
    "rule_type": "session_degradation",
    "threshold_value": 3,
    "check_interval_hours": 6,
    "min_sample_size": 1,
    "notification_channels": ["console"],
    "throttle_minutes": 360,
    "enabled": true
  }'
```

**Trigger Alert**: Submit quality metrics with very low confidence (<0.4) for multiple sessions.

---

## Testing Notification Channels

### 1. Console Notifications

Console notifications log alerts to the application logs.

**Test**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channels": ["console"]}'
```

**Verify**: Check application logs for alert output.

---

### 2. Email Notifications

Email notifications are sent via the Communications Service.

**Prerequisites**:
- Communications Service running on `http://localhost:8003`
- Email configuration in Communications Service

**Test**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["email"],
    "recipients": {
      "emails": ["test@example.com"]
    }
  }'
```

**Verify**: Check Communications Service logs and email delivery.

---

### 3. Webhook Notifications

Webhook notifications send Slack-compatible messages to URLs.

**Prerequisites**: Webhook endpoint configured (e.g., Slack webhook URL)

**Test**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["webhook"],
    "recipients": {
      "webhook_urls": ["https://hooks.slack.com/services/YOUR/WEBHOOK/URL"]
    }
  }'
```

**Verify**: Check webhook endpoint (e.g., Slack channel) for alert message.

---

## Testing Scheduled Jobs

### 1. Gap Detection Job

**Schedule**: Daily at 2:00 AM UTC (configurable via `GAP_DETECTION_SCHEDULE`)

**Manual Trigger**:

Gap detection runs as part of alert checking:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/check-now" \
  -H "Authorization: Bearer $TOKEN"
```

**Verify Execution**:

```bash
curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs?job_type=gap_detection" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 2. Quality Check Job

**Schedule**: Hourly (configurable via `QUALITY_CHECK_SCHEDULE`)

**Manual Trigger**:

```bash
curl -X POST "http://localhost:8005/api/v1/alerts/check-now" \
  -H "Authorization: Bearer $TOKEN"
```

**Verify Execution**:

```bash
curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs?job_type=quality_check" \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

### 3. Monitoring Next Run Times

Check when scheduled jobs will next execute:

```bash
curl -X GET "http://localhost:8005/api/v1/alerts/scheduler/status" \
  -H "Authorization: Bearer $TOKEN" | jq '.jobs[] | {name, next_run_time}'
```

---

## Troubleshooting

### Scheduler Not Starting

**Symptom**: `scheduler_running: false` in status response

**Solutions**:

1. Check `ENABLE_SCHEDULER` in `.env`:
   ```bash
   ENABLE_SCHEDULER=true
   ```

2. Check application logs for scheduler startup errors:
   ```bash
   grep "scheduler" logs/app.log
   ```

3. Verify cron schedule format:
   ```bash
   # Valid formats:
   GAP_DETECTION_SCHEDULE=0 2 * * *     # Daily at 2 AM
   QUALITY_CHECK_SCHEDULE=0 * * * *     # Every hour
   ```

---

### Alerts Not Triggering

**Symptom**: Manual alert check shows no alerts triggered despite meeting thresholds

**Solutions**:

1. Check if alert rule is enabled:
   ```bash
   curl -X GET "http://localhost:8005/api/v1/alerts/rules/RULE_ID" \
     -H "Authorization: Bearer $TOKEN" | jq '.enabled'
   ```

2. Check if alert is throttled:
   ```bash
   curl -X GET "http://localhost:8005/api/v1/alerts/rules/RULE_ID" \
     -H "Authorization: Bearer $TOKEN" | jq '.last_triggered_at'
   ```

3. Verify sufficient data exists (check `min_sample_size`)

4. Check alert evaluation logic in logs

---

### Email Notifications Not Sending

**Symptom**: Test alert returns success but emails not received

**Solutions**:

1. Verify Communications Service is running:
   ```bash
   curl http://localhost:8003/health
   ```

2. Check `COMMUNICATIONS_SERVICE_URL` in `.env`:
   ```bash
   COMMUNICATIONS_SERVICE_URL=http://localhost:8003
   ```

3. Check Communications Service email configuration

4. Review notification response in alert history:
   ```bash
   curl -X GET "http://localhost:8005/api/v1/alerts/history" \
     -H "Authorization: Bearer $TOKEN" | jq '.[0].notification_response'
   ```

---

### Job Execution Failures

**Symptom**: Jobs showing "failed" status in logs

**Solutions**:

1. Check job execution logs for error details:
   ```bash
   curl -X GET "http://localhost:8005/api/v1/alerts/jobs/logs?status_filter=failed" \
     -H "Authorization: Bearer $TOKEN" | jq '.logs[0].error_message'
   ```

2. Verify database connectivity

3. Check if sufficient data exists for evaluation

4. Review application logs for detailed error traces

---

### Authentication Errors

**Symptom**: 401 Unauthorized when calling alert endpoints

**Solutions**:

1. Verify token is valid:
   ```bash
   echo $TOKEN
   ```

2. Check token hasn't expired (tokens typically valid for 1 hour)

3. Verify user has admin role for admin-only endpoints

4. Re-obtain token if needed:
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:9002/auth/oauth2/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=password" \
     -d "username=adebola" \
     -d "password=password" \
     -d "client_id=frontend-client" \
     -d "client_secret=secret" | jq -r '.access_token')
   ```

---

## Testing Checklist

Use this checklist to verify Phase 5 implementation:

- [ ] Scheduler starts successfully on application startup
- [ ] Scheduler status endpoint returns job information
- [ ] Can create alert rules for all 4 rule types
- [ ] Can list all alert rules
- [ ] Can get specific alert rule details
- [ ] Can update alert rule configuration
- [ ] Can delete alert rules
- [ ] Test alerts send successfully to console
- [ ] Test alerts send successfully via email (if configured)
- [ ] Test alerts send successfully via webhook (if configured)
- [ ] Manual alert check evaluates rules correctly
- [ ] Alert history records triggered alerts
- [ ] Job execution logs capture scheduled runs
- [ ] Quality drop alerts trigger correctly
- [ ] New gaps alerts trigger correctly
- [ ] High negative feedback alerts trigger correctly
- [ ] Session degradation alerts trigger correctly
- [ ] Alert throttling prevents spam
- [ ] Scheduler stops gracefully on shutdown

---

## Next Steps

After successful Phase 5 testing:

1. Configure production alert rules based on your quality thresholds
2. Set up email/webhook integrations for production notifications
3. Monitor job execution logs regularly
4. Adjust cron schedules based on your monitoring needs
5. Review and refine alert thresholds based on real data

---

**For additional support or questions, please refer to the main README.md or Phase 5 implementation summary.**
