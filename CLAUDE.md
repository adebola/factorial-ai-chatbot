# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FactorialBot is a multi-tenant AI chat platform built with FastAPI and LangChain. It allows organizations to upload documents, scrape websites, and provide AI-powered chat responses based on their knowledge base.

## Architecture

The system consists of two main microservices:

### Chat Service (Port 8000)
- **Location**: `./chat-service/`
- **Purpose**: Handles real-time chat via WebSockets with AI responses
- **Key Components**:
  - WebSocket chat handlers with tenant isolation
  - LangChain integration for AI responses using OpenAI
  - Tenant-specific vector stores using ChromaDB
  - Conversation memory with Redis
  - RAG (Retrieval Augmented Generation) system

### Onboarding Service (Port 8001)
- **Location**: `./onboarding-service/`
- **Purpose**: Manages tenant registration and data ingestion
- **Key Components**:
  - Tenant registration and API key generation
  - Document upload and processing (PDF, DOCX, TXT)
  - Website scraping with configurable limits
  - File storage with MinIO/S3
  - Vector store population for RAG

## Development Commands

### Setup and Installation
```bash
# Start infrastructure services
docker-compose up -d postgres redis minio

# Install dependencies
cd chat-service && pip install -r requirements.txt && cd ..
cd onboarding-service && pip install -r requirements.txt && cd ..

# Copy environment files
cp chat-service/.env.example chat-service/.env
cp onboarding-service/.env.example onboarding-service/.env
```

### Running Services
```bash
# Option 1: Use startup script
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh

# Option 2: Run individually
cd chat-service
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

cd onboarding-service  
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Testing
```bash
# Run tests for chat service
cd chat-service && python -m pytest tests/

# Run tests for onboarding service
cd onboarding-service && python -m pytest tests/
```

### Database Management
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

## Multi-Tenancy Architecture

The platform implements strict tenant isolation:

### Database Level
- All models include `tenant_id` foreign key
- Queries are automatically scoped to tenant
- Shared database with logical separation

### Vector Store Level
- Each tenant has isolated ChromaDB collection: `tenant_{tenant_id}`
- Separate persistence directories per tenant
- RAG queries only access tenant-specific knowledge

### API Authentication
- Each tenant has unique API key for authentication
- All endpoints validate tenant access
- WebSocket connections are tenant-scoped

## Key Models

**IMPORTANT: All primary keys use UUIDv4 format (36-character strings). When creating new models or tables, always use `Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))` for primary keys unless explicitly specified otherwise.**

### Tenant Management
- `Tenant`: Core tenant information and configuration (UUID primary key)
- `ChatSession`: WebSocket session tracking (UUID primary key)
- `ChatMessage`: Conversation history (UUID primary key)

### Document Management
- `Document`: Uploaded file metadata and processing status (UUID primary key)
- `WebsiteIngestion`: Website scraping job tracking (UUID primary key)
- `WebsitePage`: Individual scraped page records (UUID primary key)

### Database Schema Standards
- **Primary Keys**: Always UUIDv4 strings (36 characters) for all tables
- **Foreign Keys**: Reference UUIDs as String(36) columns
- **Tenant Isolation**: All models include `tenant_id: String(36)` foreign key for multi-tenancy
- **Type Hints**: Use `str` for all ID parameters in service methods and API endpoints

## Service Communication

- **Inter-service**: HTTP APIs between chat and onboarding services
- **Client Communication**: WebSocket for chat, REST for onboarding
- **Data Flow**: Documents/websites → processing → vector store → chat responses

## External Dependencies

### Infrastructure
- **PostgreSQL**: Primary database
- **Redis**: Session storage and caching
- **MinIO/S3**: File storage
- **ChromaDB**: Vector embeddings

### AI Services
- **OpenAI API**: GPT models via LangChain
- **LangChain**: Document processing and RAG pipeline

## Environment Configuration

**CRITICAL SECURITY RULE**: Never store sensitive values (API keys, secrets, credentials, URLs) in `config.py` files. These files are checked into version control and cannot be easily overridden in Docker/Kubernetes environments.

### Environment Variable Best Practices

**✅ Always in .env files (not config.py):**
- API Keys: `OPENAI_API_KEY`, `PAYSTACK_SECRET_KEY`
- Database URLs: `DATABASE_URL`, `VECTOR_DATABASE_URL`
- Service URLs: `REDIS_URL`, `MINIO_ENDPOINT`, `CHAT_SERVICE_URL`, `ONBOARDING_SERVICE_URL`
- Authentication: `JWT_SECRET_KEY`, `SECRET_KEY`
- Credentials: `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- Webhooks: `PAYSTACK_WEBHOOK_SECRET`, `PAYMENT_CALLBACK_URL`

**✅ Safe in config.py (non-sensitive defaults):**
- API paths: `API_V1_STR = "/api/v1"`
- Service names: `PROJECT_NAME = "Chat Service"`
- Timeouts: `ACCESS_TOKEN_EXPIRE_MINUTES = 30`
- Limits: `MAX_PAGES_PER_SITE = 100`
- Currency: `DEFAULT_CURRENCY = "NGN"`

### Configuration Loading Pattern

```python
# ❌ WRONG - Never do this
class Settings(BaseSettings):
    OPENAI_API_KEY: str = "sk-default-key"  # Exposed in code!
    JWT_SECRET_KEY: str = "secret123"       # Security risk!

# ✅ CORRECT - Environment only
class Settings(BaseSettings):
    """Non-sensitive configuration only"""
    API_V1_STR: str = "/api/v1"  # Safe default
    PROJECT_NAME: str = "Service Name"
    
    class Config:
        env_file = ".env"

# Access sensitive values directly from environment
import os
api_key = os.environ.get("OPENAI_API_KEY")
```

**Why this matters:**
- Config files are committed to git and visible to all developers
- Docker/Kubernetes cannot override hardcoded values in source code
- Environment variables can be securely managed per deployment environment
- Prevents accidental exposure of credentials in logs/debugging

Critical environment variables:
- `OPENAI_API_KEY`: Required for AI functionality
- `DATABASE_URL`: PostgreSQL connection
- `REDIS_URL`: Redis connection  
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`: File storage
- `JWT_SECRET_KEY`: JWT token signing
- `SECRET_KEY`: General application secret

## File Processing Pipeline

1. **Upload**: Files stored in MinIO with tenant prefix
2. **Processing**: Content extracted based on file type
3. **Chunking**: Text split into overlapping chunks
4. **Embedding**: OpenAI embeddings generated
5. **Storage**: Vectors stored in tenant-specific ChromaDB collection

## Chat Widget System

The platform automatically generates embeddable chat widgets for tenants:

### Widget Generation
- **Automatic**: Generated during tenant registration
- **Customizable**: Uses tenant branding and colors (#5D3EC1, #C15D3E, #3EC15D)
- **Responsive**: Works on desktop and mobile devices
- **Secure**: Tenant-specific API keys embedded

### Widget Files Generated
- `chat-widget.js`: Main widget JavaScript (self-contained)
- `chat-widget.css`: Additional styling (optional)
- `demo.html`: Test page for widget preview
- `integration-guide.html`: Comprehensive integration documentation

### Widget Features
- 🎨 **Custom Branding**: Organization name and FactorialBot logo
- 💬 **Real-time Chat**: WebSocket connection for instant responses
- 📱 **Mobile Responsive**: Optimized for all screen sizes
- 🌙 **Dark Mode**: Automatic dark mode support
- 🔒 **Secure**: Bearer token authentication
- ⚡ **Lightweight**: Minimal performance impact

### API Endpoints
- `GET /api/v1/tenants/{id}/widget/generate` - Generate widget files
- `GET /api/v1/tenants/{id}/widget/chat-widget.js` - Download JavaScript
- `GET /api/v1/tenants/{id}/widget/preview` - Preview widget
- `GET /api/v1/tenants/{id}/widget/download-all` - Download ZIP package

### Integration
```html
<!-- Simple Integration -->
<script src="path/to/chat-widget.js"></script>
```

## Chat Flow

1. **Connection**: WebSocket with API key authentication
2. **Session**: Create chat session with tenant isolation
3. **Query**: User message triggers RAG search
4. **Context**: Retrieve relevant documents from vector store
5. **Generation**: LangChain generates response with context
6. **Response**: Stream back via WebSocket with sources

## Plans Management

The system includes a comprehensive subscription plans system:

### Plan Features
- **Soft Deletion**: Plans are marked as deleted, not removed
- **Usage Limits**: Document, website, and chat limits per plan
- **Pricing Tiers**: Monthly and yearly pricing options
- **Admin Controls**: Full CRUD operations for admin users only

### Default Plans
- **Free**: 5 docs, 1 website, 300 monthly chats - $0/month
- **Basic**: 25 docs, 3 websites, 3000 monthly chats - $9.99/month
- **Pro**: 100 docs, 10 websites, 15000 monthly chats - $29.99/month
- **Enterprise**: 1000 docs, 50 websites, 60000 monthly chats - $99.99/month

### Plan API Endpoints
- `POST /api/v1/plans/` - Create plan (admin only)
- `GET /api/v1/plans/` - List all plans (all users)
- `PUT /api/v1/plans/{id}` - Update plan (admin only)
- `DELETE /api/v1/plans/{id}` - Soft delete plan (admin only)

## Security Considerations

- API keys are tenant-unique and required for all operations
- Database queries include tenant_id validation
- File uploads are validated for type and size
- Vector stores are completely isolated per tenant
- WebSocket connections maintain session-level tenant binding
- Plans management restricted to admin role users
- Chat widget files contain tenant-specific API keys for secure access
- **OPENAI_API_KEY**: Always accessed via `os.environ.get("OPENAI_API_KEY")` - never through settings classes to prevent accidental commits

## Structured Logging System

Both services implement comprehensive structured logging using **Loguru + Structlog**:

### Features
- **Multi-tenant context**: All logs include `tenant_id`, `request_id`, `user_id`, `session_id`
- **Request tracking**: Unique request IDs for tracing across services
- **Performance monitoring**: Automatic timing for API requests, AI generation, vector searches
- **Environment-based output**: Pretty console logs for development, JSON for production
- **Error tracking**: Detailed error context with stack traces

### Configuration
- **Development**: `ENVIRONMENT=development` → Colorized console logs
- **Production**: `ENVIRONMENT=production` → Structured JSON logs
- **Log Level**: Set via `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR)

### Usage Examples
```python
from app.core.logging_config import get_logger, set_request_context

# Get logger
logger = get_logger("module_name")

# Set request context (automatically added to all logs)
set_request_context(
    request_id="req-123",
    tenant_id="tenant-456",
    user_id="user-789"
)

# Log with structured data
logger.info("Operation completed", 
    operation="document_upload",
    file_size=1024,
    duration_ms=150.5
)
```

### Helper Functions
- `log_api_request()` / `log_api_response()`: HTTP request/response logging
- `log_chat_message()`: Chat message tracking
- `log_ai_generation()`: AI response generation metrics
- `log_vector_search()`: Vector store operation timing
- `log_tenant_operation()`: Tenant-specific operations

## Development Guidelines for Claude Code

### Service Testing Protocol
**CRITICAL**: Only clean up processes that Claude Code starts during testing:

1. **Before Testing**: Note any running services on target ports (8000, 8001) - these belong to the user
2. **During Testing**: 
   - If you need to kill user processes to run tests, that's acceptable
   - Keep track of which processes YOU start during testing
3. **After Testing**: **ONLY** kill processes that YOU started during the exercise
   - Do NOT kill processes that were running before you started
   - Do NOT kill processes you didn't start

```bash
# Example: Only kill processes YOU started
# If you started a service with uvicorn, kill it
# If you started a background bash process, kill it
# Do NOT blindly kill all processes on ports 8000/8001
```

**Process Ownership Rules**:
- ✅ Kill: Processes started by Claude Code during the current session
- ❌ Don't Kill: User processes that existed before the exercise
- ✅ Temporary Kill: User processes needed for testing (they can restart them)

**Why this matters**: The user needs to manage their own development workflow. Only clean up what you created.