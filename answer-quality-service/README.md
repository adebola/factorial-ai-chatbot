# Answer Quality & Feedback Service

FastAPI microservice for measuring and improving RAG chatbot answer quality through user feedback, quality metrics, and knowledge gap detection.

## Features

### ✅ Implemented (Phases 1-5)

- ✅ **User Feedback Collection**: Thumbs up/down on AI responses with optional comments
- ✅ **RAG Quality Metrics**: Track retrieval scores, answer confidence, and response times
- ✅ **Basic Sentiment Analysis**: VADER sentiment detection (free, rule-based, < 1ms per analysis)
- ✅ **Session Quality Tracking**: Automatic calculation of session success based on feedback
- ✅ **Quality Warnings**: Automatic flagging of low-confidence answers, poor retrieval, slow responses
- ✅ **Event-Driven Architecture**: RabbitMQ consumer for processing chat messages
- ✅ **Event Publishing**: Publishes feedback and quality events for other services
- ✅ **Multi-Tenant Isolation**: All data isolated by tenant_id
- ✅ **Structured Logging**: Comprehensive logging with tenant context
- ✅ **Health Checks**: Kubernetes-ready liveness/readiness probes
- ✅ **API Documentation**: Auto-generated OpenAPI/Swagger docs
- ✅ **Knowledge Gap Detection**: TF-IDF clustering for identifying recurring low-quality questions
- ✅ **Admin Dashboard**: Comprehensive dashboard with trends and insights
- ✅ **CSV Export**: Export quality reports for analysis
- ✅ **Scheduled Jobs**: Automated gap detection (daily) and quality checks (hourly)
- ✅ **Alerting System**: 4 alert rule types with configurable thresholds and throttling
- ✅ **Multi-Channel Notifications**: Email, webhook, and console notifications
- ✅ **Alert Management API**: Full CRUD for alert rules with admin controls
- ✅ **Job Execution Logging**: Complete audit trail for all scheduled jobs and alerts

### 🚧 Future Enhancements

- 🚧 **Advanced ML Models**: Deep learning for sentiment and quality prediction
- 🚧 **Frontend Dashboard**: React/Vue dashboard for visualization
- 🚧 **SMS Notifications**: Mobile alerts for critical quality issues
- 🚧 **Alert Analytics**: Trend analysis and false positive detection

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL
- RabbitMQ
- Redis
- Authorization Server (for JWT validation)

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or `./venv/bin/activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Create database
createdb answer_quality_db
# Or via psql:
# PGPASSWORD=password psql -h localhost -U postgres -c "CREATE DATABASE answer_quality_db;"

# Copy environment file
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head
```

### Running the Service

```bash
# Development mode (with auto-reload)
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload

# Production mode
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8005
```

### Verify Installation

```bash
# Check health
curl http://localhost:8005/api/v1/health

# Check readiness (requires database)
curl http://localhost:8005/api/v1/health/ready

# View API documentation
open http://localhost:8005/api/v1/docs
```

## API Endpoints

### Health Checks

- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/ready` - Readiness check (validates dependencies)
- `GET /api/v1/health/live` - Liveness check

### Feedback API (`/api/v1/feedback/`)

**User Endpoints** (Requires authentication):
- `POST /api/v1/feedback/` - Submit thumbs up/down feedback
  - Body: `{ "message_id": "...", "session_id": "...", "feedback_type": "helpful|not_helpful", "comment": "..." }`
  - Returns: Feedback record with auto-calculated session quality
- `GET /api/v1/feedback/message/{message_id}` - Get feedback for a specific message
- `GET /api/v1/feedback/session/{session_id}` - Get all feedback for a session
- `GET /api/v1/feedback/stats?session_id=...` - Get feedback statistics
  - Returns: Total counts, helpful percentage, recent feedback examples

### Quality Metrics API (`/api/v1/quality/`)

**User Endpoints** (Requires authentication):
- `GET /api/v1/quality/message/{message_id}` - Get quality metrics for a specific message
  - Returns: Retrieval scores, confidence, response time, sentiment
- `GET /api/v1/quality/session/{session_id}` - Get all quality metrics for a session
- `GET /api/v1/quality/session/{session_id}/stats` - Get aggregated session statistics
  - Returns: Avg scores, low confidence count, sentiment breakdown
- `GET /api/v1/quality/stats?session_id=...` - Get overall quality statistics
  - Can filter by session or return tenant-wide stats

**Admin Endpoints** (Requires admin role):
- `GET /api/v1/quality/low-quality?limit=50` - Get messages with low quality scores
  - Returns: Messages with confidence < 0.5, sorted by lowest first

### Admin Dashboard API (`/api/v1/admin/`)

**Access Control**: Endpoints are divided into two tiers:
- **Tier 1 (Authenticated Users)**: View analytics for their own organization
- **Tier 2 (Admin Users)**: Manage gaps and perform expensive operations

#### Tier 1: Analytics Endpoints (Requires Authentication)

**Dashboard & Analytics** - Accessible to all authenticated users:
- `GET /api/v1/admin/dashboard/overview?days=7` - Get dashboard overview statistics
  - Returns: Total messages, avg scores, feedback stats, active gaps (tenant-scoped)
- `GET /api/v1/admin/dashboard/trends?days=30` - Get daily quality trends
  - Returns: Daily aggregated quality metrics and feedback (tenant-scoped)

**Knowledge Gap Viewing** - Read-only access for all authenticated users:
- `GET /api/v1/admin/gaps?status=detected&limit=50` - List knowledge gaps
  - Filter by status: detected, acknowledged, resolved (tenant-scoped)

#### Tier 2: Management Endpoints (Requires Admin Role)

**Knowledge Gap Management** - Admin only:
- `POST /api/v1/admin/gaps/detect?days=7` - Trigger knowledge gap detection
  - Uses TF-IDF clustering to find recurring low-quality questions (computationally expensive)
- `PATCH /api/v1/admin/gaps/{gap_id}/acknowledge` - Acknowledge a gap
  - Body: `{ "notes": "optional notes" }`
- `PATCH /api/v1/admin/gaps/{gap_id}/resolve` - Resolve a gap
  - Body: `{ "resolution_notes": "how it was fixed" }`

**Data Export** - Admin only:
- `GET /api/v1/admin/export/quality-report?days=30&format=csv` - Export CSV report
  - Downloads CSV with all quality metrics and feedback (bulk data export)

### Alerts & Scheduler API (`/api/v1/alerts/`)

**Access Control**: Alert management endpoints are divided into two tiers:
- **Tier 1 (Authenticated Users)**: View alert rules, history, and scheduler status
- **Tier 2 (Admin Users)**: Create, update, delete rules, and trigger manual checks

#### Tier 1: Monitoring Endpoints (Requires Authentication)

**Alert Rules Viewing** - Accessible to all authenticated users:
- `GET /api/v1/alerts/rules?enabled_only=false` - List all alert rules
  - Returns: All configured alert rules for the tenant
- `GET /api/v1/alerts/rules/{rule_id}` - Get specific alert rule details
  - Returns: Full rule configuration including thresholds and notification settings

**Alert History** - View triggered alerts:
- `GET /api/v1/alerts/history?rule_id=...&severity=...&limit=50` - View alert history
  - Filter by rule ID, severity (info/warning/critical), or get recent alerts
  - Returns: Historical record of all triggered alerts with notification results

**Scheduler Status** - Monitor background jobs:
- `GET /api/v1/alerts/scheduler/status` - Get scheduler status and next run times
  - Returns: Scheduler state, job count, and next execution times for scheduled jobs
- `GET /api/v1/alerts/jobs/logs?job_type=...&status_filter=...&limit=50` - View job execution logs
  - Filter by job type (gap_detection/quality_check) or status (success/failed)
  - Returns: Detailed logs of scheduled job executions with duration and results

#### Tier 2: Management Endpoints (Requires Admin Role)

**Alert Rule Management** - Admin only:
- `POST /api/v1/alerts/rules` - Create new alert rule
  - Body: Rule configuration with type, thresholds, notification channels
  - **Rule Types**:
    - `quality_drop` - Alert when avg confidence drops below threshold
    - `new_gaps` - Alert when N+ new knowledge gaps detected
    - `high_negative_feedback` - Alert when negative feedback rate exceeds threshold
    - `session_degradation` - Alert when multiple sessions have poor quality
- `PUT /api/v1/alerts/rules/{rule_id}` - Update existing alert rule
  - Body: Partial rule updates (threshold, enabled status, notification settings)
- `DELETE /api/v1/alerts/rules/{rule_id}` - Delete alert rule
  - Permanently removes the alert rule

**Alert Testing & Control** - Admin only:
- `POST /api/v1/alerts/test` - Send test alert notification
  - Body: `{ "channels": ["console", "email", "webhook"], "recipients": {...} }`
  - Use to verify notification channel configuration
- `POST /api/v1/alerts/check-now` - Manually trigger alert evaluation
  - Evaluates all enabled rules immediately (bypasses schedule)
  - Returns: Summary of rules checked and alerts triggered

**Notification Channels**:
- **Console**: Logs to application logs (for testing)
- **Email**: Sends via Communications Service (`COMMUNICATIONS_SERVICE_URL`)
- **Webhook**: Slack-compatible webhook integration

**Example Alert Rule Creation**:
```bash
curl -X POST http://localhost:8005/api/v1/alerts/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Low Confidence Alert",
    "rule_type": "quality_drop",
    "description": "Alert when confidence drops below 0.6",
    "threshold_value": 0.6,
    "check_interval_hours": 1,
    "min_sample_size": 5,
    "notification_channels": ["email"],
    "notification_recipients": {"emails": ["admin@example.com"]},
    "throttle_minutes": 60,
    "enabled": true
  }'
```

**Scheduled Jobs**:
- **Gap Detection**: Runs daily at 2:00 AM UTC (configurable via `GAP_DETECTION_SCHEDULE`)
- **Quality Check**: Runs hourly (configurable via `QUALITY_CHECK_SCHEDULE`)

## Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Service
ENVIRONMENT=development
PORT=8005
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/answer_quality_db

# Redis
REDIS_URL=redis://localhost:6379/4

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Authorization Server
AUTH_SERVER_URL=http://localhost:9000
JWT_ISSUER=http://localhost:9000

# Chat Service
CHAT_SERVICE_URL=http://localhost:8000

# Communications Service (for email alerts)
COMMUNICATIONS_SERVICE_URL=http://localhost:8003
ALERT_EMAIL_FROM=alerts@factorialbot.com

# Feature Flags
ENABLE_BASIC_SENTIMENT=true
ENABLE_GAP_DETECTION=true
ENABLE_SCHEDULER=true

# Scheduler Configuration (cron format)
GAP_DETECTION_SCHEDULE=0 2 * * *    # Daily at 2 AM
QUALITY_CHECK_SCHEDULE=0 * * * *    # Every hour
GAP_DETECTION_LOOKBACK_DAYS=7

# Alert Defaults
DEFAULT_ALERT_THROTTLE_MINUTES=1440
```

## Architecture

### Event-Driven Design

The service uses RabbitMQ for async communication:

**Consumes:**
- `chat.message.created` - AI responses with quality metrics

**Publishes:**
- `feedback.submitted` - User feedback events
- `knowledge.gap.detected` - Detected knowledge gaps
- `session.quality.updated` - Session quality changes

### Database Schema

- `answer_feedback` - User feedback (👍/👎) on AI responses
- `rag_quality_metrics` - Quality metrics per message (retrieval scores, confidence)
- `knowledge_gaps` - Detected gaps in the knowledge base
- `session_quality` - Aggregated session-level quality metrics
- `alert_rules` - Configurable alert rule definitions with thresholds and notification settings
- `alert_history` - Historical record of all triggered alerts with notification results
- `job_execution_logs` - Execution logs for scheduled jobs (gap detection, quality checks)

## Development

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_feedback.py -v

# Test Phase 5 (Alerts & Scheduler)
./test_phase5.sh
```

For detailed Phase 5 testing instructions, see [PHASE5_TESTING_GUIDE.md](./PHASE5_TESTING_GUIDE.md).

### Code Quality

```bash
# Format code
black app/

# Check linting
flake8 app/

# Type checking
mypy app/
```

## Integration with Other Services

### Chat Service Integration

The chat service should publish enhanced `message.created` events with quality metrics:

```json
{
  "event_type": "message.created",
  "tenant_id": "uuid",
  "session_id": "uuid",
  "message_id": "uuid",
  "message_type": "assistant",
  "quality_metrics": {
    "retrieval_score": 0.85,
    "documents_retrieved": 5,
    "answer_confidence": 0.78,
    "sources_cited": 3,
    "answer_length": 450,
    "response_time_ms": 1250
  }
}
```

## Monitoring

### Health Checks

Kubernetes/Docker health probes:

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/health/live
    port: 8005
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /api/v1/health/ready
    port: 8005
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Logging

Structured JSON logs in production, pretty console logs in development.

All logs include tenant context:
- `tenant_id`
- `user_id`
- `session_id`
- `request_id`

## License

Proprietary - FactorialSystems
