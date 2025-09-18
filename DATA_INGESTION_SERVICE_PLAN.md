# 📋 Data Ingestion Service Extraction Plan

## 🎯 **Service Name & Database**
- **Service Name**: `data-ingestion-service` (Port 8002)
- **Database Name**: `ingestion_db`
- **Purpose**: Dedicated service for document and website content ingestion, processing, and vector storage

## 🏗️ **Architecture Overview**

### Current State (What needs to be moved)
**From Onboarding Service → To Data Ingestion Service:**

#### 1. **Models** (Database Tables)
- `Document` → Move to ingestion_db
- `WebsiteIngestion` → Move to ingestion_db
- `WebsitePage` → Move to ingestion_db
- Document categorization tables (keep references)

#### 2. **Services** (Business Logic)
- `PgVectorIngestionService` → Core ingestion engine
- `DocumentProcessor` → Document processing & categorization
- `WebsiteScraper` → Website scraping & processing
- `StorageService` → File storage management
- `DocumentCategorizationService` → AI-powered categorization
- `CategorizedVectorStore` → Enhanced vector search

#### 3. **API Endpoints**
- `/api/v1/documents/*` → Document upload & management
- `/api/v1/websites/*` → Website ingestion management
- `/api/v1/search/categorized` → Enhanced search capabilities

## 🗄️ **Database Architecture**

### New `ingestion_db` Schema
```sql
-- Document management
documents                    -- Document metadata & status
document_processing_logs     -- Processing history & errors

-- Website ingestion
website_ingestions          -- Website scraping jobs
website_pages               -- Individual scraped pages
website_processing_logs     -- Scraping history & errors

-- Categorization metadata (local references)
document_category_assignments  -- Document-category relationships
document_tag_assignments      -- Document-tag relationships

-- Processing queues & jobs
ingestion_jobs              -- Background job management
processing_queue            -- Queue for async processing
```

### Shared Resources
- **vector_db**: Remains shared across all services
- **onboard_db**: Retains category/tag definitions, tenant management
- **Redis**: Shared caching and job queues
- **MinIO**: Shared file storage

## 🔄 **Service Communication Pattern**

### Inter-Service API Calls
1. **Authentication**: All services validate tokens via authorization-server
2. **Category Lookup**: Ingestion service → Onboarding service for category definitions
3. **Usage Tracking**: Ingestion service → Onboarding service for usage limits
4. **Notifications**: Ingestion service → Chat service for new content

### Event-Driven Architecture (Optional Enhancement)
- Use RabbitMQ for async job processing
- Publish events: `document.uploaded`, `website.scraped`, `content.categorized`
- Enable loose coupling between services

## 📋 **Implementation Steps**

### Phase 1: New Service Foundation (Week 1)
1. **Create service structure**
   - `data-ingestion-service/` directory
   - FastAPI application setup
   - Database configuration & Alembic
   - Environment configuration
   - Docker setup

2. **Database migration**
   - Create `ingestion_db` database
   - Migrate document/website models
   - Set up Alembic migrations
   - Create database initialization scripts

### Phase 2: Core Logic Migration (Week 2)
3. **Move services layer**
   - Copy & adapt ingestion services
   - Update database connections
   - Implement inter-service communication
   - Add proper error handling & logging

4. **Move API endpoints**
   - Copy document/website API routes
   - Update authentication to use shared auth
   - Implement proper request/response handling
   - Add comprehensive API documentation

### Phase 3: Data Migration & Integration (Week 3)
5. **Data Migration & Backup**
   - **Pre-migration backup**
     - Full database backup of onboard_db
     - Export critical tables to SQL files
     - Document current record counts for validation
   - **Migration execution**
     - Export existing documents/websites from onboard_db
     - Import into new ingestion_db with transaction safety
     - Verify data integrity with checksums
     - Update foreign key references
   - **Post-migration validation**
     - Compare record counts between databases
     - Verify all relationships intact
     - Test sample queries for data consistency

6. **Service integration**
   - Update onboarding service to call ingestion APIs
   - Remove old ingestion code from onboarding
   - Update chat service vector access (if needed)
   - Configure nginx/gateway routing

### Phase 4: Enhancement & Optimization (Week 4)
7. **Performance optimization**
   - Implement background job processing
   - Add caching strategies
   - Optimize vector operations
   - Add monitoring & metrics

8. **Production deployment**
   - Docker compose updates
   - Production configuration
   - Load balancing setup
   - Monitoring & alerting

## 🔗 **API Integration Points**

### New Ingestion Service APIs
```bash
# Document Management
POST   /api/v1/documents/upload          # Upload & process documents
GET    /api/v1/documents/                # List tenant documents
DELETE /api/v1/documents/{id}            # Delete document
POST   /api/v1/documents/{id}/reprocess  # Reprocess document

# Website Management
POST   /api/v1/websites/ingest           # Start website ingestion
GET    /api/v1/ingestions/               # List ingestions
DELETE /api/v1/ingestions/{id}           # Delete ingestion
POST   /api/v1/ingestions/{id}/retry     # Retry failed ingestion

# Enhanced Search
GET    /api/v1/search/categorized        # Category-filtered search
POST   /api/v1/search/semantic           # Semantic similarity search
```

### Modified Onboarding Service
```bash
# Keep category/tag management
GET/POST/PUT/DELETE /api/v1/categories/* # Category definitions
GET/POST/PUT/DELETE /api/v1/tags/*       # Tag definitions

# Proxy calls to ingestion service
POST   /api/v1/documents/* → ingestion-service
POST   /api/v1/websites/*  → ingestion-service
```

## 🚨 **Migration Considerations**

### Data Consistency
- **Atomic migration**: Ensure zero data loss during transition
- **Foreign key updates**: Update category/tag references
- **Vector data**: Ensure vector_db remains consistent

### Service Dependencies
- **Startup order**: ingestion-service depends on onboarding for categories
- **Health checks**: Implement proper health endpoints
- **Circuit breakers**: Handle service unavailability gracefully

### Backward Compatibility
- **API versioning**: Maintain v1 APIs during transition
- **Gradual migration**: Phase out old endpoints slowly
- **Documentation**: Update all API documentation

## 🎯 **Benefits of This Architecture**

### 1. **Separation of Concerns**
- **Onboarding**: Focus on tenant/user management, billing, categories
- **Ingestion**: Specialized for content processing & vector operations
- **Chat**: Focus on real-time communication & AI responses

### 2. **Scalability**
- **Independent scaling**: Scale ingestion service based on upload volume
- **Background processing**: Offload heavy processing from user requests
- **Resource optimization**: Dedicated resources for CPU-intensive tasks

### 3. **Maintainability**
- **Focused codebase**: Each service has clear responsibilities
- **Independent deployments**: Deploy ingestion features without affecting chat
- **Team specialization**: Teams can focus on specific domains

### 4. **Performance**
- **Optimized processing**: Dedicated resources for document/website processing
- **Caching strategies**: Service-specific caching for different use cases
- **Queue management**: Better handling of processing backlogs

## 🔧 **Technology Stack**

### Data Ingestion Service
- **Framework**: FastAPI (consistency with existing services)
- **Database**: PostgreSQL (`ingestion_db`)
- **Vector Store**: Shared `vector_db` with pgvector
- **File Storage**: Shared MinIO/S3
- **Authentication**: Shared OAuth2 authorization server
- **Caching**: Redis (shared)
- **Background Jobs**: Celery/RQ (optional enhancement)

### Development Tools
- **Alembic**: Database migrations
- **Docker**: Containerization
- **Pytest**: Testing framework
- **Poetry/pip**: Dependency management

## 📁 **File Structure**

```
data-ingestion-service/
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI application
│   ├── api/
│   │   ├── __init__.py
│   │   ├── documents.py               # Document upload endpoints
│   │   ├── websites.py                # Website ingestion endpoints
│   │   └── search.py                  # Enhanced search endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # Configuration settings
│   │   ├── database.py                # Database connections
│   │   └── logging_config.py          # Structured logging
│   ├── models/
│   │   ├── __init__.py
│   │   ├── document.py                # Document models
│   │   ├── website.py                 # Website ingestion models
│   │   └── categorization.py          # Category assignment models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_processor.py      # Document processing logic
│   │   ├── website_scraper.py         # Website scraping logic
│   │   ├── vector_ingestion.py        # Vector database operations
│   │   ├── storage_service.py         # MinIO/S3 operations
│   │   ├── categorization_service.py  # AI categorization
│   │   └── dependencies.py            # Authentication & dependencies
│   └── background/
│       ├── __init__.py
│       ├── tasks.py                   # Background job definitions
│       └── workers.py                 # Job worker configuration
├── ingestion_migrations/               # Alembic migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── test_documents.py
│   ├── test_websites.py
│   └── test_search.py
├── requirements.txt                    # Python dependencies
├── Dockerfile                          # Container definition
├── .env.example                        # Environment template
└── README.md                          # Service documentation
```

## 🔐 **Data Migration & Backup Strategy**

### Pre-Migration Steps
1. **Full Database Backup**
   ```bash
   # Create timestamped backup directory
   BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
   mkdir -p backups/${BACKUP_DATE}

   # Full database backup
   pg_dump -h localhost -U postgres -d onboard_db > backups/${BACKUP_DATE}/onboard_db_full.sql

   # Individual table backups for safety
   pg_dump -h localhost -U postgres -d onboard_db -t documents > backups/${BACKUP_DATE}/documents.sql
   pg_dump -h localhost -U postgres -d onboard_db -t website_ingestions > backups/${BACKUP_DATE}/website_ingestions.sql
   pg_dump -h localhost -U postgres -d onboard_db -t website_pages > backups/${BACKUP_DATE}/website_pages.sql
   pg_dump -h localhost -U postgres -d onboard_db -t document_category_assignments > backups/${BACKUP_DATE}/document_category_assignments.sql
   pg_dump -h localhost -U postgres -d onboard_db -t document_tag_assignments > backups/${BACKUP_DATE}/document_tag_assignments.sql
   ```

2. **Document Current State**
   ```sql
   -- Record counts for validation
   SELECT 'documents' as table_name, COUNT(*) as record_count FROM documents
   UNION ALL
   SELECT 'website_ingestions', COUNT(*) FROM website_ingestions
   UNION ALL
   SELECT 'website_pages', COUNT(*) FROM website_pages
   UNION ALL
   SELECT 'document_category_assignments', COUNT(*) FROM document_category_assignments
   UNION ALL
   SELECT 'document_tag_assignments', COUNT(*) FROM document_tag_assignments;
   ```

3. **Generate Data Checksums**
   ```sql
   -- Create checksums for critical tables
   SELECT MD5(STRING_AGG(id::text || tenant_id || filename, ',' ORDER BY id))
   AS documents_checksum FROM documents;
   ```

### Migration Execution

#### Step 1: Schema Migration
```sql
-- Create tables in ingestion_db with same structure
-- This will be handled by Alembic migrations in the new service
```

#### Step 2: Data Transfer
```bash
# Use pg_dump with data-only flag to transfer data
pg_dump -h localhost -U postgres -d onboard_db \
  --data-only \
  --table=documents \
  --table=website_ingestions \
  --table=website_pages \
  | psql -h localhost -U postgres -d ingestion_db

# Transfer assignment tables (these may stay or be duplicated)
pg_dump -h localhost -U postgres -d onboard_db \
  --data-only \
  --table=document_category_assignments \
  --table=document_tag_assignments \
  | psql -h localhost -U postgres -d ingestion_db
```

#### Step 3: Validation
```sql
-- Verify record counts match
SELECT
  (SELECT COUNT(*) FROM ingestion_db.documents) =
  (SELECT COUNT(*) FROM onboard_db.documents) AS documents_match,
  (SELECT COUNT(*) FROM ingestion_db.website_ingestions) =
  (SELECT COUNT(*) FROM onboard_db.website_ingestions) AS ingestions_match;

-- Verify data integrity with checksums
-- Compare checksums between databases
```

### Post-Migration Cleanup

#### Phase 1: Soft Decommission (Week 1 after migration)
```python
# Create Alembic migration to rename old tables
"""rename_migrated_tables_for_cleanup

Revision ID: xxx
Revises: yyy
"""

def upgrade():
    # Rename tables to indicate they're deprecated
    op.rename_table('documents', '_deprecated_documents')
    op.rename_table('website_ingestions', '_deprecated_website_ingestions')
    op.rename_table('website_pages', '_deprecated_website_pages')

    # Add deprecation notice
    op.execute("""
        COMMENT ON TABLE _deprecated_documents IS
        'DEPRECATED: Migrated to ingestion_db on [DATE]. Will be removed on [DATE+30]';
    """)

def downgrade():
    # Restore original table names if rollback needed
    op.rename_table('_deprecated_documents', 'documents')
    op.rename_table('_deprecated_website_ingestions', 'website_ingestions')
    op.rename_table('_deprecated_website_pages', 'website_pages')
```

#### Phase 2: Hard Deletion (Week 4 after migration)
```python
# Final Alembic migration to remove tables
"""remove_migrated_tables_final

Revision ID: zzz
Revises: xxx
"""

def upgrade():
    # Drop deprecated tables after confirming migration success
    op.drop_table('_deprecated_documents')
    op.drop_table('_deprecated_website_ingestions')
    op.drop_table('_deprecated_website_pages')

    # Drop related indexes
    op.drop_index('idx_documents_tenant_id')
    op.drop_index('idx_website_ingestions_tenant_id')
    op.drop_index('idx_website_pages_ingestion_id')

def downgrade():
    # Restore tables from backup if needed
    # This would require manual restoration from backups
    pass
```

### Rollback Plan

#### Immediate Rollback (if migration fails)
```bash
# Stop new ingestion service
docker-compose stop data-ingestion-service

# Restore onboard_db to original state
psql -h localhost -U postgres -d onboard_db < backups/${BACKUP_DATE}/onboard_db_full.sql

# Revert Alembic migrations in onboarding service
cd onboarding-service
alembic downgrade -1

# Restart onboarding service with original configuration
docker-compose up -d onboarding-service
```

#### Gradual Rollback (if issues found after migration)
```bash
# Keep both services running
# Route traffic back to onboarding service
# Copy any new data from ingestion_db back to onboard_db
pg_dump -h localhost -U postgres -d ingestion_db \
  --data-only \
  --table=documents \
  --where="created_at > '[MIGRATION_DATE]'" \
  | psql -h localhost -U postgres -d onboard_db
```

### Data Verification Checklist

- [ ] All record counts match between databases
- [ ] Foreign key relationships maintained
- [ ] No orphaned records in assignment tables
- [ ] Vector database references updated
- [ ] MinIO/S3 file references intact
- [ ] API endpoints return correct data
- [ ] Search functionality works properly
- [ ] Category/tag assignments preserved
- [ ] Audit trail maintained
- [ ] Performance metrics acceptable

## 🔄 **Migration Script Example**

```python
# migrate_data.py - Example data migration script
import psycopg2
from psycopg2.extras import RealDictCursor

def migrate_documents():
    """Migrate documents from onboard_db to ingestion_db"""

    # Connect to source database
    source_conn = psycopg2.connect("postgresql://user:pass@localhost/onboard_db")
    source_cur = source_conn.cursor(cursor_factory=RealDictCursor)

    # Connect to target database
    target_conn = psycopg2.connect("postgresql://user:pass@localhost/ingestion_db")
    target_cur = target_conn.cursor()

    # Fetch all documents
    source_cur.execute("""
        SELECT * FROM documents
        ORDER BY created_at
    """)

    documents = source_cur.fetchall()

    # Insert into new database
    for doc in documents:
        target_cur.execute("""
            INSERT INTO documents
            (id, tenant_id, filename, file_path, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            doc['id'], doc['tenant_id'], doc['filename'],
            doc['file_path'], doc['status'], doc['created_at']
        ))

    target_conn.commit()
    print(f"Migrated {len(documents)} documents")

    # Close connections
    source_cur.close()
    source_conn.close()
    target_cur.close()
    target_conn.close()

if __name__ == "__main__":
    migrate_documents()
```

## 📊 **Success Metrics**

### Performance Metrics
- **Document processing time**: < 5 seconds for standard PDFs
- **Website scraping rate**: 10+ pages per minute
- **Vector search latency**: < 100ms for categorized search
- **API response time**: < 200ms for document upload

### Operational Metrics
- **Service availability**: 99.9% uptime
- **Error rate**: < 0.1% for processing jobs
- **Queue backlog**: < 100 pending jobs
- **Memory usage**: < 2GB per container

### Business Metrics
- **Documents processed/day**: Support 10,000+ documents
- **Websites scraped/day**: Support 500+ websites
- **Concurrent uploads**: Handle 100+ simultaneous uploads
- **Search queries/second**: Support 50+ QPS

## 🚀 **Next Steps**

1. **Review & Approval**: Review this plan with the team
2. **Environment Setup**: Prepare development environment
3. **Database Creation**: Create `ingestion_db` database
4. **Service Scaffold**: Create initial service structure
5. **Begin Migration**: Start with Phase 1 implementation

This plan provides a comprehensive roadmap for extracting the ingestion logic into a dedicated service while maintaining system stability and improving overall architecture.