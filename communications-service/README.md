# Communications Service

A FastAPI-based microservice for handling email, SMS, and WhatsApp communications for the FactorialBot platform.

## Features

- 📧 Email sending via SendGrid
- 📱 SMS and WhatsApp messaging via Twilio
- 🔒 JWT-based authentication
- 📊 Structured logging with request tracing
- 🗄️ PostgreSQL database with SQLAlchemy
- 🔄 Database migrations with Alembic
- 🐰 RabbitMQ message queuing
- 📝 Template management system
- 🚀 Multi-tenant architecture

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL
- RabbitMQ (optional, for message queuing)

### Setup

1. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Create database:**
   ```bash
   createdb communications_db
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Start the service:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
   ```

## Environment Variables

### Required Configuration

```bash
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/communications_db

# JWT Authentication
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256

# SendGrid (Email)
SENDGRID_API_KEY=your-sendgrid-api-key
SENDGRID_FROM_EMAIL=noreply@yourdomain.com
SENDGRID_FROM_NAME=Your App Name

# Twilio (SMS/WhatsApp)
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_FROM_PHONE=+1234567890

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Optional Configuration

```bash
# RabbitMQ (for message queuing)
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest

# Rate Limiting
EMAIL_RATE_LIMIT=100
SMS_RATE_LIMIT=50

# Provider Selection
SMS_PROVIDER=twilio  # or 'mock' for testing
EMAIL_PROVIDER=sendgrid  # or 'mock' for testing
```

## API Documentation

Once the service is running, visit:
- **Interactive API docs:** http://localhost:8003/api/v1/docs
- **ReDoc documentation:** http://localhost:8003/api/v1/redoc

## Development

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Quality

```bash
# Format code
black app/

# Sort imports
isort app/

# Type checking
mypy app/

# Linting
flake8 app/
```

## Docker

### Build and Run

```bash
# Build the image
docker build -t communications-service .

# Run with docker-compose
docker-compose up communications-service
```

### Docker Compose

The service is configured to work with the main project's docker-compose setup:

```yaml
# Already configured in ../docker-compose.yml
communications-service:
  build:
    context: ./communications-service
    dockerfile: Dockerfile
  ports:
    - "8003:8003"
  environment:
    - DATABASE_URL=postgresql://postgres:password@postgres:5432/communications_db
  depends_on:
    - postgres
    - minio
```

## API Endpoints

### Email

- `POST /api/v1/email/send` - Send email
- `POST /api/v1/email/send-bulk` - Send bulk emails
- `GET /api/v1/email/delivery-status/{message_id}` - Check delivery status

### SMS

- `POST /api/v1/sms/send` - Send SMS
- `POST /api/v1/sms/send-bulk` - Send bulk SMS
- `GET /api/v1/sms/delivery-status/{message_id}` - Check delivery status

### Templates

- `GET /api/v1/templates/` - List templates
- `POST /api/v1/templates/` - Create template
- `GET /api/v1/templates/{template_id}` - Get template
- `PUT /api/v1/templates/{template_id}` - Update template
- `DELETE /api/v1/templates/{template_id}` - Delete template

### Health & Monitoring

- `GET /health` - Health check
- `GET /` - Service info

## Architecture

### Multi-tenant Design

- All data is isolated by `tenant_id`
- JWT tokens contain tenant context
- Database queries are automatically scoped to tenant

### Logging

Structured logging with request tracing:
- Request ID tracking across services
- Tenant context in all logs
- Performance metrics
- Error tracking with stack traces

### Error Handling

- Consistent error responses
- Proper HTTP status codes
- Detailed error messages for development
- Sanitized errors for production

## Troubleshooting

### Common Issues

1. **Database connection failed:**
   ```bash
   # Check PostgreSQL is running
   pg_isready -h localhost -p 5432

   # Verify database exists
   psql -h localhost -U postgres -l
   ```

2. **SendGrid/Twilio errors:**
   ```bash
   # Verify API keys are set
   echo $SENDGRID_API_KEY
   echo $TWILIO_ACCOUNT_SID
   ```

3. **Import errors:**
   ```bash
   # Ensure virtual environment is activated
   which python

   # Reinstall dependencies
   pip install -r requirements.txt --force-reinstall
   ```

4. **Package installation fails (Python 3.13+):**
   ```bash
   # For Python 3.13+, use the alternative requirements file
   pip install -r requirements-python313.txt

   # Or install problematic packages individually with newer versions
   pip install "psycopg[binary]>=3.1.0"
   pip install "pydantic>=2.8.0"
   pip install "pydantic-settings>=2.4.0"

   # You may also need to install build tools
   pip install --upgrade wheel setuptools build
   ```

5. **Wheel building errors:**
   ```bash
   # Install build dependencies
   pip install --upgrade pip wheel setuptools

   # Try installing without cache
   pip install --no-cache-dir -r requirements.txt
   ```

### Logs

Check logs for detailed error information:
```bash
# Development (colorized logs)
tail -f logs/communications.log

# Production (JSON logs)
docker logs communications-service
```

## License

This project is part of the FactorialBot platform.