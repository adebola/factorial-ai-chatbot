# FactorialBot - Multi-Tenant AI Chat Platform

A scalable, multi-tenant AI chat application built with FastAPI and LangChain that allows organizations to upload documents, scrape their websites, and provide AI-powered chat responses based on their knowledge base.

## 🏗️ Architecture

The platform consists of two main microservices:

### 1. Chat Service (Port 8000)
- **WebSocket-based chat** with real-time communication
- **LangChain integration** for AI responses using OpenAI
- **Multi-tenant vector stores** using ChromaDB
- **Conversation memory** with Redis
- **Tenant isolation** for security

### 2. Onboarding Service (Port 8001)
- **Tenant registration** and management
- **Document upload** and processing (PDF, DOCX, TXT)
- **Website scraping** and content ingestion
- **File storage** with MinIO/S3
- **Vector store population** for RAG

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- OpenAI API Key

### 1. Setup Environment
```bash
# Copy environment files
cp chat-service/.env.example chat-service/.env
cp onboarding-service/.env.example onboarding-service/.env

# Edit .env files and add your OPENAI_API_KEY
```

### 2. Install Dependencies
```bash
# Chat Service
cd chat-service
pip install -r requirements.txt
cd ..

# Onboarding Service
cd onboarding-service
pip install -r requirements.txt
cd ..
```

### 3. Start Infrastructure
```bash
# Start PostgreSQL, Redis, and MinIO
docker-compose up -d postgres redis minio
```

### 4. Run Services
```bash
# Option A: Use the startup script
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh

# Option B: Run manually
# Terminal 1 - Chat Service
cd chat-service
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Onboarding Service
cd onboarding-service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## 📚 API Usage

### 1. Register a New Tenant
```bash
curl -X POST "http://localhost:8001/api/v1/tenants/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "domain": "acme.com",
    "website_url": "https://acme.com"
  }'
```

Response includes `api_key` for authentication.

### 2. Upload Documents
```bash
curl -X POST "http://localhost:8001/api/v1/documents/upload" \
  -F "api_key=YOUR_API_KEY" \
  -F "file=@document.pdf"
```

### 3. Ingest Website
```bash
curl -X POST "http://localhost:8001/api/v1/websites/ingest" \
  -F "api_key=YOUR_API_KEY" \
  -F "website_url=https://your-website.com"
```

### 4. WebSocket Chat
Connect to `ws://localhost:8000/api/v1/ws/chat?api_key=YOUR_API_KEY`

Message format:
```json
{"message": "What services do you offer?"}
```

## 🏭 Production Deployment

### Using Docker Compose
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f chat-service
docker-compose logs -f onboarding-service
```

### Environment Configuration
Key environment variables to configure:

**Database:**
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string

**Storage:**
- `MINIO_ENDPOINT`: S3/MinIO endpoint
- `MINIO_ACCESS_KEY` & `MINIO_SECRET_KEY`: Storage credentials

**AI:**
- `OPENAI_API_KEY`: OpenAI API key for LangChain

**Security:**
- `SECRET_KEY`: JWT signing key (generate random)

## 🔧 Development

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

### Testing
```bash
# Run tests for chat service
cd chat-service
python -m pytest tests/

# Run tests for onboarding service
cd onboarding-service
python -m pytest tests/
```

## 🌐 Service Endpoints

### Chat Service (8000)
- `GET /`: Health check
- `GET /health`: Service health status
- `WS /api/v1/ws/chat`: WebSocket chat endpoint

### Onboarding Service (8001)
- `GET /`: Health check
- `GET /health`: Service health status
- `POST /api/v1/tenants/`: Create tenant
- `GET /api/v1/tenants/{id}`: Get tenant
- `POST /api/v1/documents/upload`: Upload document
- `POST /api/v1/websites/ingest`: Start website scraping
- `GET /api/v1/ingestions/{id}/status`: Check ingestion status

## 📊 Monitoring

### Access Management Interfaces
- **MinIO Console**: http://localhost:9001 (admin/password)
- **PostgreSQL**: localhost:5432 (user/password)
- **Redis**: localhost:6379

### Health Checks
- Chat Service: http://localhost:8000/health
- Onboarding Service: http://localhost:8001/health

## 🛡️ Security Features

- **API Key Authentication**: Each tenant has a unique API key
- **Tenant Isolation**: Data segregation at database and vector store levels
- **Rate Limiting**: Configurable limits for document processing and scraping
- **File Validation**: Restricted file types and sizes for uploads

## 🔮 Features

### Current
- ✅ Multi-tenant architecture with complete data isolation
- ✅ Document upload and processing (PDF, DOCX, TXT)
- ✅ Website scraping with configurable limits
- ✅ Real-time WebSocket chat with conversation memory
- ✅ RAG-based responses using tenant-specific knowledge bases
- ✅ Vector embeddings with ChromaDB
- ✅ File storage with MinIO/S3 compatibility
- ✅ Docker containerization

### Future Enhancements
- 🔲 Billing and subscription management microservice
- 🔲 Advanced analytics and usage tracking
- 🔲 Multi-language support
- 🔲 Custom AI model integration
- 🔲 Advanced security features (OAuth, SSO)
- 🔲 API rate limiting and quotas
- 🔲 Horizontal scaling with Kubernetes

## 📄 License

This project is proprietary to Factorial Systems.