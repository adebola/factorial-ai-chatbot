# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ChatCraft** is a multi-tenant AI chat platform built with FastAPI and LangChain. It allows organizations to upload documents, scrape websites, and provide AI-powered chat responses based on their knowledge base.

**Note**: While the repository directory is named "factorialbot" (legacy), the application is called **ChatCraft**. All user-facing content, emails, and documentation should use "ChatCraft" as the product name.

## Architecture

The system consists of three main microservices:

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

### Authorization Server (Port 9000)
- **Location**: `./authorization-server/`
- **Purpose**: OAuth 2.0 authentication and authorization using Spring Authorization Server
- **Key Components**:
  - OAuth 2.0 authorization flows (Authorization Code, Client Credentials)
  - JWT token issuance and validation
  - Client registration and management
  - User authentication and consent management
  - PKCE (Proof Key for Code Exchange) support
- **Migration Plan**: Will eventually replace custom JWT authentication in onboarding service

## OAuth2 Client Management

**IMPORTANT ARCHITECTURAL DECISION**: The system uses a **single OAuth2 client** for all tenants, not per-tenant clients.

### Key Principles
- **Single Client Architecture**: The entire application uses only one OAuth2 registered client
- **No Client Creation During Registration**: When tenants register, no OAuth2 clients are automatically created
- **Manual Client Management**: OAuth2 clients are managed separately from tenant registration process
- **Tenant Isolation**: Multi-tenancy is handled at the user/data level, not at the OAuth2 client level

### Implementation Details
- Tenant registration process only creates `Tenant` and `User` records
- OAuth2 client credentials are managed independently and shared across all tenants
- The single OAuth2 client handles all authorization flows for all tenants
- User authentication resolves tenant context after login, not during OAuth2 flow

### When OAuth2 Client Management is Needed
OAuth2 client creation, modification, or additional client functionality should only be implemented when explicitly requested by the project owner. The current architecture intentionally keeps tenant registration simple and separate from OAuth2 client management.

## Development Commands

### Setup and Installation
```bash
# Start infrastructure services
docker-compose up -d postgres redis minio

# Install dependencies
cd chat-service && pip install -r requirements.txt && cd ..
cd onboarding-service && pip install -r requirements.txt && cd ..
cd authorization-server && mvn clean install && cd ..

# Copy environment files
cp chat-service/.env chat-service/.env
cp onboarding-service/.env onboarding-service/.env
cp authorization-server/.env authorization-server/.env
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

cd authorization-server
mvn spring-boot:run
```

### Testing

#### Test Credentials
For testing OAuth2 authentication and API endpoints, use the following credentials:
```
Username: adebola
Password: password
Client ID: frontend-client  
Client Secret: secret
```

These credentials can be used to:
- Generate access tokens for testing
- Authenticate API requests
- Test tenant-specific functionality
- Run integration tests with the authorization server

#### Running Tests
```bash
# Run tests for chat service
cd chat-service && python -m pytest tests/

# Run tests for onboarding service
cd onboarding-service && python -m pytest tests/

# Run specific test file (e.g., dependencies tests)
cd onboarding-service && python -m pytest tests/test_dependencies.py -v

# Run integration tests (requires running services)
cd onboarding-service && python -m pytest tests/ -m integration

# Run tests for authorization server
cd authorization-server && mvn test
```

#### OAuth2 Token Generation for Testing
```bash
# Get an access token using curl
curl -X POST http://localhost:9000/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=adebola" \
  -d "password=password" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret"

# The response will include:
# - access_token: JWT token for API authentication  
# - refresh_token: Token for refreshing access
# - tenant_id: Extracted from token claims
```

### Database Management

#### Alembic Migrations (Application Models)
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

#### Vector Database Schema Changes
**IMPORTANT**: Vector database schema changes are NOT managed by Alembic. When making changes to vector database schemas or any DDL that affects the vector database:

1. Create DDL files in `docker-build/db-init/` directory
2. Follow naming convention: `{ordered-number}-{relevant-narrative}.sql`
3. Examples:
   - `001-create-vector-tables.sql`
   - `002-add-vector-indexes.sql` 
   - `003-update-vector-constraints.sql`

```bash
# Example: Creating a new vector schema file
# docker-build/db-init/004-add-tenant-vector-partitions.sql
```

These files are executed during database initialization and should contain all necessary DDL for vector database functionality.

## Multi-Tenancy Architecture

The platform implements **loose-multitenant** architecture pattern:

### User Authentication (Loose-Multitenant Pattern)
- **Global user uniqueness**: Email addresses are unique across ALL tenants
- **No tenant selection**: Users login with email + password only
- **Automatic tenant resolution**: System determines user's tenant after authentication
- **One user = One tenant**: Each user belongs to exactly one tenant
- **Email conflict resolution**: Invitation system appends tenant domain suffix for conflicts

### Database Level
- All models include `tenant_id` foreign key for data isolation
- Users have global unique constraints on email and username
- Post-authentication queries are tenant-scoped for data security
- Shared database with logical separation

### Vector Store Level
- Each tenant has isolated ChromaDB collection: `tenant_{tenant_id}`
- Separate persistence directories per tenant
- RAG queries only access tenant-specific knowledge

### API Authentication Patterns
- **OAuth2 flows**: Use global authentication, then tenant context is resolved
- **WebSocket connections**: Still use tenant API keys for real-time chat
- **REST APIs**: Support both global auth and tenant-scoped operations

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

- **Inter-service**: HTTP APIs between chat, onboarding, and authorization services
- **Client Communication**: WebSocket for chat, REST for onboarding/auth
- **Authentication Flow**: OAuth 2.0 via authorization server (future migration)
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
- `GET /api/v1/widget/generate` - Generate widget files
- `GET /api/v1/widget/chat-widget.js` - Download JavaScript
- `GET /api/v1/widget/chat-widget.css` - Download CSS
- `GET /api/v1/widget/chat-widget.html` - Download demo HTML
- `GET /api/v1/widget/integration-guide.html` - Download integration guide
- `GET /api/v1/widget/preview` - Preview widget
- `GET /api/v1/widget/download-all` - Download ZIP package
- `GET /api/v1/widget/status` - Get widget status

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

## Scheduled Jobs and User Context

**CRITICAL**: Scheduled background jobs (APScheduler) run without HTTP request context, meaning **no access token is available**.

### The Problem:
- JWT claims (`email`, `full_name`, `tenant_id`) are only available during authenticated API requests
- Scheduled jobs like trial expiration checks, subscription renewals, etc. run independently
- Cannot use `validate_token()` or access `claims.email` / `claims.full_name` in scheduled jobs

### Solution Pattern:
When designing features that need user information in scheduled jobs:

1. **Store user data at creation time** (when token IS available):
```python
# In API endpoint (has token access)
@router.post("/subscriptions")
async def create_subscription(
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    subscription = Subscription(
        tenant_id=claims.tenant_id,
        user_email=claims.email,        # Store for later use
        user_full_name=claims.full_name, # Store for later use
        # ... other fields
    )
```

2. **Use stored data in scheduled jobs** (no token needed):
```python
# In scheduled job (NO token available)
def check_trial_expirations():
    subscriptions = db.query(Subscription).filter(...).all()

    for sub in subscriptions:
        email_publisher.publish_trial_expiring_email(
            tenant_id=sub.tenant_id,
            to_email=sub.user_email,      # From database, not token
            to_name=sub.user_full_name,   # From database, not token
            days_remaining=3
        )
```

### Best Practices:
- Add `user_email` and `user_full_name` columns to models that will be used by scheduled jobs
- Populate these fields during creation/update when JWT token is available
- Never assume `validate_token()` or JWT claims are accessible outside API request handlers
- For service-to-service calls, use dedicated service authentication (not user tokens)

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

### Python Dependency Management
**CRITICAL - ALWAYS UPDATE requirements.txt**: When adding any Python library to the project:

1. **Install the library**: `pip install <library-name>`
2. **IMMEDIATELY update requirements.txt**: Add the library with its version to the appropriate service's requirements.txt file
3. **Verify the entry**: Ensure the exact library name and version are in requirements.txt

**Why this is critical**:
- Docker builds rely SOLELY on requirements.txt files
- Development environments may have libraries installed that aren't in requirements.txt
- Missing entries cause production container failures with "ModuleNotFoundError"
- The build process cannot detect missing dependencies until runtime

**Example workflow**:
```bash
# WRONG - Only installing locally
pip install redis

# CORRECT - Install AND update requirements.txt
pip install redis
echo "redis==5.0.1" >> onboarding-service/requirements.txt
```

**Common mistakes to avoid**:
- ❌ Installing a library locally but forgetting to add it to requirements.txt
- ❌ Using `pip freeze > requirements.txt` which may include unneeded dependencies
- ❌ Adding a library import in code without updating requirements.txt
- ✅ Always add the specific version to requirements.txt immediately after installation

**Services with requirements.txt**:
- `chat-service/requirements.txt` - Chat service dependencies
- `onboarding-service/requirements.txt` - Onboarding service dependencies

### Service Testing Protocol
**CRITICAL**: Only clean up processes that Claude Code starts during testing:

1. **Before Testing**: Note any running services on target ports (8000, 8001, 9000) - these belong to the user
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
# Do NOT blindly kill all processes on ports 8000/8001/9000
```

**Process Ownership Rules**:
- ✅ Kill: Processes started by Claude Code during the current session
- ❌ Don't Kill: User processes that existed before the exercise
- ✅ Temporary Kill: User processes needed for testing (they can restart them)

**Why this matters**: The user needs to manage their own development workflow. Only clean up what you created.

### Test File Management for FastAPI Projects
**CRITICAL - NEVER DELETE TEST FILES**: When creating test files for FastAPI projects:

1. **Always create test files in the `tests/` folder** of the appropriate service
2. **NEVER delete test files after creation** - the user will decide which tests to keep or remove
3. **Keep all test files permanently** - even after testing is complete

**Test File Organization**:
```
service-name/
├── app/
│   ├── api/
│   ├── models/
│   └── services/
└── tests/
    ├── test_api_plans.py          # Keep forever
    ├── test_api_subscriptions.py  # Keep forever
    ├── test_service_plan.py       # Keep forever
    └── test_integration.py        # Keep forever
```

**Why this is critical**:
- Test files are valuable documentation of expected behavior
- They serve as regression tests for future changes
- The user maintains the test suite and decides what to keep
- Deleting tests removes valuable coverage and documentation
- Tests can be run repeatedly during development

**What NOT to do**:
- ❌ Delete test files after running them
- ❌ Delete test files to "clean up" after implementation
- ❌ Remove tests that are "no longer needed"
- ❌ Delete tests because the feature is complete

**What TO do**:
- ✅ Create test files in `tests/` directory
- ✅ Leave all test files in place after creation
- ✅ Let the user decide which tests to keep or delete
- ✅ Add new tests as features are added

## Spring Boot Development Guidelines

### Lombok Usage
**NEVER use `@Data` annotation** - it's too broad and can cause issues with JPA entities, circular references, and unwanted methods.

**✅ Use specific Lombok annotations:**
- `@Getter` - Generate getters only
- `@Setter` - Generate setters only  
- `@ToString` - Generate toString() method
- `@EqualsAndHashCode` - Generate equals() and hashCode() methods
- `@NoArgsConstructor` - Generate no-args constructor
- `@AllArgsConstructor` - Generate constructor with all fields
- `@RequiredArgsConstructor` - Generate constructor with required fields (final/non-null)
- `@Builder` - Generate builder pattern

**Examples:**
```java
// ✅ CORRECT - Specific annotations
@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User {
    private String id;
    private String name;
}

// ❌ WRONG - Avoid @Data
@Data  // Don't use this!
public class User {
    private String id;
    private String name;
}
```

**Why this matters:**
- `@Data` includes `@ToString`, `@EqualsAndHashCode`, `@Getter`, `@Setter`, and `@RequiredArgsConstructor`
- This can cause issues with JPA entities (circular references, lazy loading problems)
- Makes debugging harder when you don't control which methods are generated
- Can expose sensitive fields in `toString()` output
- Better to be explicit about what methods you need

## FastAPI Authentication Guidelines

### Proper HTTP Status Codes for Authentication

**CRITICAL**: All FastAPI services must return proper HTTP status codes for authentication failures.

**Authentication Setup Pattern**:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# IMPORTANT: Always use auto_error=False to control status codes
security = HTTPBearer(auto_error=False)

async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenClaims:
    """Validate OAuth2 token and extract claims"""

    # Check if credentials were provided
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # NOT 403!
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    # ... rest of validation logic
```

**Status Code Rules**:
- **401 Unauthorized**: Use for authentication failures
  - Missing authorization header
  - Invalid token format
  - Expired token
  - Token validation failed
- **403 Forbidden**: Use for authorization failures
  - Valid token but insufficient permissions
  - Admin-only endpoints accessed by regular users
  - Resource access denied

**Why this matters**:
- FastAPI's `HTTPBearer()` defaults to returning 403 for missing/invalid credentials
- This violates HTTP semantics where 401 means "not authenticated" and 403 means "authenticated but not authorized"
- Using `auto_error=False` allows proper control of status codes
- Consistent status codes across all services improve client error handling