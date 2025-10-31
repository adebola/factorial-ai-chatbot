# Phase 5: Scheduled Jobs & Alerting System - Implementation Summary

## Overview

Phase 5 introduces a comprehensive scheduled jobs and alerting system to the Answer Quality & Feedback Service. This system enables automated quality monitoring, proactive issue detection, and multi-channel notifications for quality degradation events.

**Implementation Date**: October 2025
**Status**: ✅ Complete

---

## What Was Implemented

### 1. Background Scheduler Service

**File**: `app/services/scheduler.py`

A robust background job scheduler using APScheduler that:

- Runs periodic tasks using cron-based triggers
- Manages two scheduled jobs:
  - **Gap Detection**: Daily at 2:00 AM UTC (configurable)
  - **Quality Check**: Hourly (configurable)
- Provides graceful startup and shutdown
- Logs all job executions to database
- Supports job coalescing and instance limits

**Key Features**:
- AsyncIOScheduler for non-blocking execution
- UTC timezone for consistency
- Error handling with fallback to service continuation
- Status monitoring endpoint

---

### 2. Alert Manager Service

**File**: `app/services/alert_manager.py`

Intelligent alert rule evaluation and notification triggering:

**Alert Rule Types**:
1. **Quality Drop**: Triggers when average answer confidence falls below threshold
2. **New Gaps**: Triggers when N or more new knowledge gaps are detected
3. **High Negative Feedback**: Triggers when negative feedback rate exceeds threshold
4. **Session Degradation**: Triggers when multiple sessions have poor quality

**Key Features**:
- Throttling to prevent alert spam
- Dynamic severity calculation (info/warning/critical)
- Tenant-scoped alert evaluation
- Comprehensive alert history logging
- Minimum sample size requirements

---

### 3. Notification Client Service

**File**: `app/services/notification_client.py`

Multi-channel notification delivery system:

**Supported Channels**:
1. **Console**: Logs alerts to application logs (for testing)
2. **Email**: Sends via Communications Service (port 8003)
3. **Webhook**: Slack-compatible webhook integration

**Key Features**:
- Graceful channel failure handling
- Detailed notification result tracking
- Customizable recipients per channel
- Rich alert formatting

---

### 4. Database Models

#### AlertRule Model

**File**: `app/models/alert_rule.py`

Stores configurable alert rule definitions:

```python
- id: UUID primary key
- tenant_id: Multi-tenant isolation
- name: Rule name
- rule_type: One of 4 types
- description: Optional description
- threshold_value: Trigger threshold
- check_interval_hours: Evaluation frequency
- min_sample_size: Minimum data required
- notification_channels: List of channels
- notification_recipients: Channel-specific recipients
- throttle_minutes: Minimum time between alerts
- enabled: Enable/disable flag
- last_triggered_at: Last alert timestamp
```

#### AlertHistory Model

**File**: `app/models/alert_history.py`

Records all triggered alerts:

```python
- id: UUID primary key
- tenant_id: Multi-tenant isolation
- rule_id: Reference to alert rule
- rule_name: Denormalized for history
- rule_type: Alert type
- severity: info/warning/critical
- alert_message: Human-readable message
- alert_data: Full alert context (JSON)
- notification_sent: Success flag
- notification_channels_used: Channels attempted
- notification_response: Detailed results (JSON)
- notification_error: Error if failed
- triggered_at: When alert triggered
- processed_at: When notifications sent
```

#### JobExecutionLog Model

**File**: `app/models/job_log.py`

Tracks scheduled job executions:

```python
- id: UUID primary key
- tenant_id: Null for system-wide jobs
- job_name: Job identifier
- job_type: gap_detection/quality_check
- status: success/failed/partial
- started_at: Execution start time
- completed_at: Execution end time
- duration_ms: Execution duration
- result_summary: Job results (JSON)
- error_message: Error if failed
- triggered_by: scheduler/manual
```

---

### 5. API Endpoints

**File**: `app/api/alerts.py`

Comprehensive API for alert management:

#### Alert Rules Management

- **POST /api/v1/alerts/rules** - Create alert rule (admin only)
- **GET /api/v1/alerts/rules** - List alert rules (authenticated)
  - Query param: `enabled_only` - Filter enabled rules only
- **GET /api/v1/alerts/rules/{rule_id}** - Get specific rule (authenticated)
- **PUT /api/v1/alerts/rules/{rule_id}** - Update alert rule (admin only)
- **DELETE /api/v1/alerts/rules/{rule_id}** - Delete alert rule (admin only)

#### Alert History

- **GET /api/v1/alerts/history** - View alert history (authenticated)
  - Query params: `rule_id`, `severity`, `limit`

#### Testing & Utilities

- **POST /api/v1/alerts/test** - Send test alert (admin only)
- **POST /api/v1/alerts/check-now** - Manual alert check (admin only)

#### Scheduler Monitoring

- **GET /api/v1/alerts/scheduler/status** - View scheduler status (authenticated)
- **GET /api/v1/alerts/jobs/logs** - View job execution logs (authenticated)
  - Query params: `job_type`, `status_filter`, `limit`

---

### 6. Database Migration

**File**: `alembic/versions/17d05ab982ab_add_alert_rules_alert_history_and_job_.py`

Creates three new tables:

1. **alert_rules**: Stores alert rule configurations
2. **alert_history**: Records all triggered alerts
3. **job_execution_logs**: Tracks scheduled job runs

All tables include:
- Proper indexes for performance
- JSON columns for flexible data storage
- Timestamps for audit trails
- Tenant isolation where applicable

---

### 7. Configuration Updates

#### config.py

Added settings for scheduler and alerting:

```python
# Scheduler & Background Jobs
ENABLE_SCHEDULER: bool = True
GAP_DETECTION_SCHEDULE: str = "0 2 * * *"
GAP_DETECTION_LOOKBACK_DAYS: int = 7
QUALITY_CHECK_SCHEDULE: str = "0 * * * *"

# Communications Service (for alert emails)
COMMUNICATIONS_SERVICE_URL: str = "http://localhost:8003"
ALERT_EMAIL_FROM: str = "alerts@factorialbot.com"

# Alert Defaults
DEFAULT_ALERT_THROTTLE_MINUTES: int = 1440
```

#### .env

Added corresponding environment variables with development defaults.

---

### 8. Dependencies

**File**: `requirements.txt`

Added scheduler dependencies:

```
APScheduler==3.10.4
pytz==2023.3
```

---

### 9. Main Application Integration

**File**: `app/main.py`

Integrated scheduler lifecycle management:

- Import `background_scheduler` from `app.services.scheduler`
- Import `alerts` router from `app.api`
- Start scheduler in application startup
- Stop scheduler in application shutdown
- Register alerts router with `/api/v1/alerts` prefix

---

### 10. Testing Artifacts

#### test_phase5.sh

Comprehensive automated test script that:

- Obtains JWT access token
- Tests all alert management endpoints
- Creates alert rules for all 4 types
- Sends test alerts
- Triggers manual alert checks
- Views alert history and job logs
- Validates scheduler status
- Provides detailed colored output

#### PHASE5_TESTING_GUIDE.md

Detailed testing documentation covering:

- Prerequisites and setup
- Quick start guide
- Manual testing procedures for all endpoints
- Testing each alert rule type
- Testing notification channels
- Testing scheduled jobs
- Troubleshooting common issues
- Testing checklist

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │          Background Scheduler (APScheduler)          │ │
│  │                                                      │ │
│  │  ┌──────────────────┐    ┌──────────────────────┐  │ │
│  │  │ Gap Detection    │    │ Quality Check        │  │ │
│  │  │ Job (Daily)      │    │ Job (Hourly)         │  │ │
│  │  └────────┬─────────┘    └──────────┬───────────┘  │ │
│  └───────────┼──────────────────────────┼──────────────┘ │
│              │                          │                │
│              ▼                          ▼                │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              Alert Manager Service                   │ │
│  │  - Evaluate alert rules                             │ │
│  │  - Calculate severity                               │ │
│  │  - Check throttling                                 │ │
│  │  - Trigger notifications                            │ │
│  └────────────────────────┬─────────────────────────────┘ │
│                           │                              │
│                           ▼                              │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           Notification Client Service                │ │
│  │  - Console notifications                             │ │
│  │  - Email via Communications Service                  │ │
│  │  - Webhook (Slack-compatible)                        │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                      API Endpoints                          │
│  - Alert Rules CRUD                                         │
│  - Alert History                                            │
│  - Test Alerts                                              │
│  - Manual Checks                                            │
│  - Scheduler Status                                         │
│  - Job Logs                                                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
           ┌───────────────────────────────┐
           │      PostgreSQL Database      │
           │  - alert_rules                │
           │  - alert_history              │
           │  - job_execution_logs         │
           └───────────────────────────────┘
```

---

## Alert Rule Types Explained

### 1. Quality Drop

**Purpose**: Detect when answer quality degrades

**How It Works**:
1. Queries average `answer_confidence` from `rag_quality_metrics`
2. Filters by `check_interval_hours` time window
3. Requires minimum `min_sample_size` metrics
4. Triggers if average < `threshold_value`

**Example Use Case**: Alert when confidence drops below 0.6 over the last hour

---

### 2. New Gaps

**Purpose**: Detect new knowledge gaps in the system

**How It Works**:
1. Counts new records in `knowledge_gaps` table
2. Filters by `check_interval_hours` time window
3. Filters for `status = "detected"`
4. Triggers if count >= `threshold_value`

**Example Use Case**: Alert when 3+ new gaps detected in last 24 hours

---

### 3. High Negative Feedback

**Purpose**: Detect excessive negative user feedback

**How It Works**:
1. Counts `not_helpful` vs `helpful` feedback
2. Filters by `check_interval_hours` time window
3. Requires minimum `min_sample_size` feedback entries
4. Calculates negative feedback rate
5. Triggers if rate > `threshold_value`

**Example Use Case**: Alert when negative feedback exceeds 30% over 12 hours

---

### 4. Session Degradation

**Purpose**: Detect when multiple chat sessions have poor quality

**How It Works**:
1. Counts distinct sessions with very low confidence (<0.4)
2. Filters by `check_interval_hours` time window
3. Triggers if session count >= `threshold_value`

**Example Use Case**: Alert when 5+ sessions have poor quality in 6 hours

---

## Notification Channel Details

### Console Notifications

- **Destination**: Application logs
- **Format**: Structured JSON log entry
- **Use Case**: Development/testing
- **Configuration**: None required

### Email Notifications

- **Destination**: Email addresses via Communications Service
- **Format**: HTML email with alert details
- **Use Case**: Production alerting
- **Configuration**:
  - `COMMUNICATIONS_SERVICE_URL` must point to running service
  - Communications Service must have email provider configured
  - `ALERT_EMAIL_FROM` sets sender address

### Webhook Notifications

- **Destination**: Webhook URLs (Slack-compatible)
- **Format**: Slack-compatible JSON payload
- **Use Case**: Integration with Slack, Teams, etc.
- **Configuration**:
  - Recipients must include `webhook_urls` array
  - URLs should be Slack webhook endpoints or compatible services

---

## Severity Calculation

Alerts are automatically assigned severity based on threshold deviation:

```python
if deviation > 50%:
    severity = "critical"
elif deviation > 20%:
    severity = "warning"
else:
    severity = "info"
```

**Example**:
- Threshold: 0.6 confidence
- Actual: 0.3 confidence
- Deviation: (0.6 - 0.3) / 0.6 = 50%
- **Severity: critical**

---

## Throttling

Alert throttling prevents notification spam:

- Each rule has a `throttle_minutes` setting (default: 1440 = 24 hours)
- After an alert triggers, the same rule won't trigger again until throttle period expires
- Throttle timer resets with each trigger
- `last_triggered_at` timestamp tracks last alert

**Example**: A rule with 60-minute throttle can only alert once per hour, even if conditions persist.

---

## Scheduled Jobs

### Gap Detection Job

**ID**: `gap_detection`
**Schedule**: `0 2 * * *` (Daily at 2:00 AM UTC)
**Function**: Runs gap detection for all tenants
**Logs**: Records tenants processed and gaps detected

**Execution Flow**:
1. Query all unique tenant IDs from quality metrics
2. For each tenant, run gap detector with 7-day lookback
3. Count and log detected gaps
4. Record execution in job_execution_logs

### Quality Check Job

**ID**: `quality_check`
**Schedule**: `0 * * * *` (Every hour)
**Function**: Evaluates all enabled alert rules for all tenants
**Logs**: Records rules checked and alerts triggered

**Execution Flow**:
1. Query all enabled alert rules
2. For each rule, evaluate against current data
3. Trigger alerts where thresholds exceeded
4. Send notifications via configured channels
5. Record execution in job_execution_logs

---

## Configuration Options

### Scheduler Control

```bash
# Enable/disable entire scheduler
ENABLE_SCHEDULER=true

# Configure job schedules (cron format)
GAP_DETECTION_SCHEDULE=0 2 * * *      # Daily at 2 AM
QUALITY_CHECK_SCHEDULE=0 * * * *      # Every hour
GAP_DETECTION_LOOKBACK_DAYS=7
```

### Communications Integration

```bash
# Communications Service for emails
COMMUNICATIONS_SERVICE_URL=http://localhost:8003
ALERT_EMAIL_FROM=alerts@factorialbot.com
```

### Alert Defaults

```bash
# Default throttle period (minutes)
DEFAULT_ALERT_THROTTLE_MINUTES=1440
```

---

## API Authentication

All alert endpoints require JWT authentication:

- **Admin-only endpoints**: `require_admin` dependency
  - POST /rules (create)
  - PUT /rules/{id} (update)
  - DELETE /rules/{id} (delete)
  - POST /test (send test alert)
  - POST /check-now (manual check)

- **Authenticated endpoints**: `validate_token` dependency
  - GET /rules (list)
  - GET /rules/{id} (get)
  - GET /history (view history)
  - GET /scheduler/status (status)
  - GET /jobs/logs (logs)

**Token Format**: Bearer token in Authorization header

---

## Testing Summary

### Automated Testing

Run the comprehensive test script:

```bash
./test_phase5.sh
```

Tests performed:
- ✅ Token acquisition
- ✅ Scheduler status check
- ✅ Alert rule creation (all 4 types)
- ✅ Alert rule listing
- ✅ Alert rule retrieval
- ✅ Alert rule updates
- ✅ Test alert sending
- ✅ Manual alert checking
- ✅ Alert history viewing
- ✅ Job logs viewing
- ✅ Alert rule deletion

### Manual Testing

Refer to `PHASE5_TESTING_GUIDE.md` for detailed manual testing procedures.

---

## Files Changed/Created

### New Files

1. `app/models/alert_rule.py` - AlertRule model
2. `app/models/alert_history.py` - AlertHistory model
3. `app/models/job_log.py` - JobExecutionLog model
4. `app/services/scheduler.py` - Background scheduler service
5. `app/services/alert_manager.py` - Alert evaluation and triggering
6. `app/services/notification_client.py` - Multi-channel notifications
7. `app/api/alerts.py` - Alert management API endpoints
8. `alembic/versions/17d05ab982ab_*.py` - Database migration
9. `test_phase5.sh` - Automated test script
10. `PHASE5_TESTING_GUIDE.md` - Testing documentation
11. `PHASE5_SUMMARY.md` - This file

### Modified Files

1. `app/main.py` - Integrated scheduler lifecycle and alerts router
2. `app/core/config.py` - Added scheduler and alert settings
3. `.env` - Added scheduler and alert configuration
4. `requirements.txt` - Added APScheduler and pytz dependencies
5. `alembic/env.py` - Imported new models for migration

---

## Performance Considerations

### Database Indexes

All new tables include indexes on:
- `tenant_id` (for multi-tenant queries)
- `id` (primary key, automatic)
- `created_at` / `triggered_at` / `started_at` (for time-based queries)
- `job_name`, `job_type` (for log filtering)
- `rule_id` (for alert history queries)

### Query Optimization

- Alert evaluation uses aggregation queries to minimize data transfer
- Time-based filters prevent full table scans
- Minimum sample size requirements prevent evaluation on insufficient data

### Scheduler Efficiency

- Cron triggers only run at specified times (not continuous polling)
- Coalescing prevents duplicate runs if previous execution still running
- max_instances=1 ensures only one instance per job type

---

## Security Considerations

### Authentication & Authorization

- All endpoints require valid JWT tokens
- Admin-only operations protected by `require_admin` dependency
- Tenant isolation enforced at query level

### Data Privacy

- Alert rules scoped to tenant_id
- Alert history scoped to tenant_id
- Job logs include tenant_id where applicable

### Notification Security

- Email/webhook credentials managed in Communications Service
- No sensitive credentials stored in alert rules
- Notification responses logged for audit trail

---

## Monitoring & Observability

### Logging

All major operations logged with structured logging:

- Scheduler startup/shutdown
- Job executions (start, complete, fail)
- Alert rule evaluation
- Alert triggering
- Notification sending

### Metrics

Track the following via logs and database:

- Job execution duration (`duration_ms`)
- Alert trigger frequency (`alert_history.triggered_at`)
- Notification success rates (`notification_sent`)
- Rule evaluation results (`job_execution_logs.result_summary`)

### Health Checks

- Scheduler status endpoint shows running state and next run times
- Job logs show execution history and failure rates
- Alert history shows notification delivery success

---

## Future Enhancements

Potential improvements for Phase 5:

1. **Alert Channels**:
   - SMS notifications
   - In-app notifications
   - PagerDuty/Opsgenie integration

2. **Alert Rules**:
   - Custom alert rules with user-defined queries
   - Alert rule templates
   - Multi-condition rules (AND/OR logic)

3. **Scheduler**:
   - On-demand job triggering via API
   - Job retry logic with exponential backoff
   - Job dependency management

4. **Notifications**:
   - Rich email templates with charts/graphs
   - Notification preferences per user
   - Alert aggregation (daily digest)

5. **Analytics**:
   - Alert trend analysis
   - False positive detection
   - Optimal threshold recommendations

---

## Known Limitations

1. **Email Dependency**: Email notifications require Communications Service to be running
2. **Cron Precision**: Scheduler uses cron syntax, minimum granularity is 1 minute
3. **Tenant Discovery**: Gap detection job discovers tenants from quality metrics table (assumes at least one metric per tenant)
4. **Throttling Granularity**: Throttling is per-rule, not per-condition or per-tenant
5. **Webhook Format**: Webhooks use Slack-compatible format only

---

## Troubleshooting

For common issues and solutions, refer to the **Troubleshooting** section in `PHASE5_TESTING_GUIDE.md`.

Quick checklist:

- ✅ Scheduler enabled in `.env`?
- ✅ Database migration applied?
- ✅ APScheduler dependencies installed?
- ✅ Communications Service running (for emails)?
- ✅ Valid JWT token for testing?
- ✅ Admin role for admin endpoints?

---

## Conclusion

Phase 5 successfully implements a production-ready scheduled jobs and alerting system for the Answer Quality & Feedback Service. The system provides:

- **Automated monitoring** through scheduled quality checks
- **Proactive alerting** for quality degradation
- **Flexible notification** through multiple channels
- **Comprehensive audit trail** via alert history and job logs
- **Easy management** through REST APIs
- **Extensible architecture** for future enhancements

The implementation follows best practices for:
- Error handling and graceful degradation
- Multi-tenancy and data isolation
- Authentication and authorization
- Logging and observability
- Testing and documentation

Phase 5 is ready for production deployment and will provide valuable insights into chatbot answer quality over time.

---

**For testing instructions, see**: `PHASE5_TESTING_GUIDE.md`
**For automated testing, run**: `./test_phase5.sh`
**For API documentation, visit**: `http://localhost:8005/api/v1/docs`
