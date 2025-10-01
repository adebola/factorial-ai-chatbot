# Workflow Service

The Workflow Service is a core component of the FactorialBot platform that enables tenants to create, manage, and execute complex conversational workflows with conditional logic, multi-step interactions, and seamless integration with the existing chat system.

## Features

### Core Functionality
- **Workflow Management**: Create, update, delete, and manage conversational workflows
- **Trigger Detection**: Automatically detect when user messages should trigger workflows
- **Execution Engine**: Execute workflow steps with state management and variable handling
- **Multi-tenant Support**: Complete tenant isolation for all workflow operations
- **Template System**: Reusable workflow templates for common use cases

### Workflow Types Supported
- **Message Steps**: Send predefined messages to users
- **Choice Steps**: Present multiple options for user selection
- **Input Steps**: Collect user input with validation
- **Condition Steps**: Evaluate logic for branching workflows
- **Action Steps**: Execute integrations (API calls, emails, etc.)
- **Sub-workflows**: Reusable workflow components

### Integration Points
- **Chat Service**: Seamless handover between AI chat and workflows
- **Communications Service**: Send emails/SMS through workflow actions
- **Authorization Service**: JWT-based authentication and tenant resolution
- **Gateway Service**: Centralized routing and CORS handling

## Architecture

### Service Structure
```
workflow-service/
├── app/
│   ├── api/                    # FastAPI route handlers
│   │   ├── workflows.py        # Workflow CRUD operations
│   │   ├── executions.py       # Execution management
│   │   └── triggers.py         # Trigger detection
│   ├── core/                   # Core configuration
│   │   ├── config.py          # Application settings
│   │   ├── database.py        # Database connection
│   │   └── logging_config.py  # Structured logging
│   ├── models/                 # SQLAlchemy models
│   │   ├── workflow.py        # Workflow definitions
│   │   └── execution.py       # Execution tracking
│   ├── schemas/                # Pydantic schemas
│   │   ├── workflow.py        # Workflow API schemas
│   │   └── execution.py       # Execution API schemas
│   ├── services/               # Business logic
│   │   ├── workflow_parser.py  # YAML/JSON parsing
│   │   └── trigger_detector.py # Trigger detection
│   └── main.py                # FastAPI application
├── alembic/                   # Database migrations
├── Dockerfile                 # Container configuration
└── requirements.txt          # Python dependencies
```

### Database Schema
- **workflows**: Workflow definitions and metadata
- **workflow_versions**: Version history and rollback capability
- **workflow_executions**: Runtime execution tracking
- **workflow_states**: Current state of active conversations
- **step_executions**: Individual step execution logs
- **workflow_analytics**: Performance metrics and analytics
- **workflow_templates**: Reusable workflow templates

## API Endpoints

### Workflow Management
- `GET /api/v1/workflows/` - List all workflows for tenant
- `GET /api/v1/workflows/{id}` - Get specific workflow
- `POST /api/v1/workflows/` - Create new workflow
- `PUT /api/v1/workflows/{id}` - Update workflow
- `DELETE /api/v1/workflows/{id}` - Delete workflow
- `POST /api/v1/workflows/{id}/activate` - Activate workflow
- `POST /api/v1/workflows/{id}/deactivate` - Deactivate workflow

### Execution Management
- `GET /api/v1/executions/` - List workflow executions
- `GET /api/v1/executions/{id}` - Get specific execution
- `POST /api/v1/executions/start` - Start new workflow execution
- `POST /api/v1/executions/step` - Execute next workflow step
- `GET /api/v1/executions/session/{session_id}/state` - Get session state
- `POST /api/v1/executions/{id}/cancel` - Cancel execution

### Trigger Detection
- `POST /api/v1/triggers/check` - Check if message triggers workflows
- `GET /api/v1/triggers/workflows/{id}/test` - Test workflow trigger

## Workflow Definition Format

Workflows are defined using a structured YAML/JSON format:

```yaml
name: "Lead Qualification"
description: "Qualify potential leads and collect contact information"
trigger:
  type: "message"
  conditions: ["pricing", "demo", "trial", "cost"]
steps:
  - id: "greeting"
    type: "message"
    content: "I'd love to help you learn more about our pricing! Let me ask a few questions."
    next_step: "company_size"

  - id: "company_size"
    type: "choice"
    content: "What's your company size?"
    options: ["1-10 employees", "11-50 employees", "51+ employees"]
    variable: "company_size"
    next_step: "collect_email"

  - id: "collect_email"
    type: "input"
    content: "Great! What's your email address?"
    variable: "email"
    next_step: "send_pricing"

  - id: "send_pricing"
    type: "action"
    action: "send_email"
    params:
      template: "pricing_info"
      to: "{{email}}"
variables:
  company_size: ""
  email: ""
```

## User Experience Flow

### For Administrators
1. **Workflow Creation**: Use management dashboard to create workflows
2. **Template Library**: Access pre-built workflow templates
3. **Testing Environment**: Test workflows before activation
4. **Analytics Dashboard**: Monitor workflow performance and metrics

### For End Users
1. **Natural Conversation**: Workflows feel like seamless chat interaction
2. **Progress Indicators**: Visual feedback on multi-step workflows
3. **Context Preservation**: Conversation history maintained throughout
4. **Fallback Options**: Easy return to AI chat when needed

## Example Use Cases

### Lead Qualification Workflow
1. User mentions "pricing" or "demo"
2. Workflow triggers and collects company information
3. Qualifies lead based on company size
4. Sends appropriate pricing information via email
5. Creates lead record in CRM system

### Customer Support Escalation
1. User mentions "help" or "issue"
2. Workflow collects issue type and details
3. Routes to appropriate support queue
4. Creates support ticket with context
5. Sends confirmation to user

### Onboarding Workflow
1. New user joins chat
2. Workflow guides through setup steps
3. Collects preferences and configuration
4. Creates initial workspace
5. Sends welcome email with next steps

## Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 12+
- Redis 6+

### Installation
```bash
cd workflow-service
pip install -r requirements.txt
cp .env.example .env  # Configure environment variables
```

### Database Setup
```bash
# Create database
createdb workflow_db

# Run migrations
alembic upgrade head
```

### Running the Service
```bash
# Development mode
python -m app.main

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

### Docker Deployment
```bash
docker build -t workflow-service .
docker run -p 8002:8002 workflow-service
```

## Configuration

### Environment Variables
```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/workflow_db

# Redis
REDIS_URL=redis://localhost:6379/2

# External Services
CHAT_SERVICE_URL=http://localhost:8000
COMMUNICATIONS_SERVICE_URL=http://localhost:8003
AUTHORIZATION_SERVICE_URL=http://localhost:9000

# Security
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ISSUER=http://localhost:9000/auth
```

## Integration with Chat Service

The workflow service integrates with the chat service through HTTP API calls:

1. **Trigger Detection**: Chat service calls `/api/v1/triggers/check` for each user message
2. **Workflow Execution**: When triggered, chat hands over to workflow execution
3. **State Management**: Workflow state is maintained per chat session
4. **Context Handover**: Seamless transition between AI chat and workflows

## Monitoring and Analytics

### Structured Logging
- JSON format for production environments
- Request/response tracking with unique IDs
- Workflow execution metrics and performance data
- Error tracking with detailed context

### Performance Metrics
- Workflow completion rates
- Average execution time
- User engagement metrics
- Trigger accuracy and confidence scores

## Security Considerations

- **Tenant Isolation**: All workflows are scoped to specific tenants
- **JWT Authentication**: Secure API access using OAuth2 tokens
- **Input Validation**: All user inputs are validated and sanitized
- **Rate Limiting**: Prevent abuse of workflow execution
- **Audit Logging**: Complete audit trail of all workflow operations

## Future Enhancements

- **Visual Workflow Builder**: Drag-and-drop interface for workflow creation
- **Machine Learning**: AI-powered trigger optimization
- **Advanced Integrations**: Webhook support and custom function execution
- **A/B Testing**: Workflow variant testing and optimization
- **Voice Integration**: Support for voice-based workflow interactions

## Contributing

When contributing to the workflow service:

1. Follow existing code patterns and structure
2. Add comprehensive tests for new features
3. Update documentation for API changes
4. Use structured logging for observability
5. Ensure tenant isolation is maintained

## Support

For questions or issues related to the workflow service:
- Check the API documentation at `/api/v1/docs`
- Review logs for debugging information
- Ensure all dependencies are properly configured
- Verify database connectivity and migrations