# Microservice Split Analysis - FactorialBot Backend

## Current State Analysis

**Onboarding Service Size**: 35 Python files, ~9,484 lines of code - **moderately sized but manageable**

**Current Responsibilities**:
1. **Tenant Management** - Registration, authentication, API keys
2. **Content Ingestion** - Document upload, website scraping, vector processing
3. **Subscription & Billing** - Plans, payments, usage tracking
4. **Chat Widget Generation** - Widget creation and management
5. **Authentication** - JWT auth (temporary, migrating to OAuth server)

## Initial Recommendation: Split into 3 Microservices

### 1. **Tenant Service** (Port 8001)
```
- Tenant registration & management
- API key generation
- Basic authentication (until OAuth migration complete)
- User profiles
```

### 2. **Content Ingestion Service** (Port 8002) 
```
- Document upload & processing
- Website scraping
- Vector embeddings generation
- File storage management
- Chat widget generation
```

### 3. **Billing Service** (Port 8003)
```
- Subscription plans management
- Payment processing (Paystack)
- Usage tracking & limits
- Billing webhooks
```

## Why Split Now?

### ✅ **Clear Business Boundaries**
- Each service has distinct business logic
- Different scaling requirements
- Independent deployment needs

### ✅ **Team Scalability** 
- Different teams can own different services
- Billing team can focus on payments/subscriptions
- Content team can focus on ingestion pipeline

### ✅ **Technical Benefits**
- **Billing Service**: Can scale independently during billing cycles
- **Content Service**: Can handle heavy processing workloads separately
- **Tenant Service**: Lightweight, high-availability user management

### ✅ **Operational Benefits**
- Billing service can have different security/compliance requirements
- Content service can have different resource allocation
- Easier to troubleshoot domain-specific issues

## Migration Strategy

1. **Phase 1**: Extract Billing Service first (cleanest separation)
2. **Phase 2**: Extract Content Ingestion Service  
3. **Phase 3**: Keep Tenant Service as core identity provider

**Initial Verdict**: **Yes, split now** - The service has reached the complexity threshold where the benefits of separation outweigh the coordination costs.

---

## UPDATED RECOMMENDATION: Considering Spring Authorization Server Migration

*Based on the planned migration of authentication and tenant management to Spring Authorization Server*

Given that **authentication and tenant management will move to Spring Authorization Server**, here's the revised strategy:

### 1. **Content & Ingestion Service** (Port 8002)
```
Responsibilities:
- Document upload & processing  
- Website scraping & ingestion
- Vector embeddings generation
- File storage management (MinIO)
- Chat widget generation & management
- Document/website usage tracking
```

### 2. **Billing & Subscription Service** (Port 8003)
```
Responsibilities:
- Subscription plans management
- Payment processing (Paystack integration)
- Usage limits & quota enforcement
- Billing cycle management
- Payment webhooks & callbacks
- Invoice generation
- Plan switching logic
```

### 3. **Spring Authorization Server** (Port 9000) - Enhanced
```
New Responsibilities (in addition to OAuth):
- Tenant registration & management
- User profile management
- API key generation & validation
- Role-based access control (admin/user)
- Client credentials for service-to-service auth
```

## Why This Split is Better

### ✅ **Cleaner Separation of Concerns**
- **Content Service**: Focuses purely on data processing pipeline
- **Billing Service**: Handles all financial operations
- **Auth Server**: Centralized identity and tenant management

### ✅ **Spring Boot Advantages for Tenant Management**
- Better OAuth 2.0/OIDC compliance
- Enterprise-grade security features
- Better integration with existing Java ecosystem
- Robust session management

### ✅ **Simplified Architecture**
- Fewer service-to-service calls
- Content and Billing services are pure business logic
- Auth server handles all cross-cutting concerns

## Migration Strategy

### **Phase 1: Enhance Spring Authorization Server**
1. Add tenant management endpoints
2. Add user profile management
3. Implement API key generation
4. Add RBAC (Role-Based Access Control)

### **Phase 2: Extract Billing Service**
1. Move payment-related endpoints
2. Move subscription management
3. Move usage tracking
4. Update to call Auth Server for tenant validation

### **Phase 3: Rename & Refactor Remaining Service**
1. Remove auth & tenant code from onboarding service
2. Rename to "Content Ingestion Service"
3. Update to use Auth Server for authentication
4. Focus purely on content processing pipeline

## Service Communication Pattern

```
Client → Spring Auth Server (authentication)
Client → Content Service (with JWT from Auth Server)
Client → Billing Service (with JWT from Auth Server)

Billing Service → Auth Server (tenant validation)
Content Service → Auth Server (tenant validation)
```

**Updated Verdict**: **Split into 2 Python services + enhanced Spring Auth Server** - This creates a cleaner architecture with centralized identity management and better separation of business concerns.

---

## IMPLEMENTATION UPDATE: Settings System Added

*Added September 1, 2025*

### New Settings Functionality Added to Onboarding Service

A comprehensive tenant settings system has been implemented to manage:

- **Company Branding**: Primary/secondary colors, company logo upload
- **Chat Widget Customization**: Hover text, welcome messages, chat window titles
- **Extensible Architecture**: JSON field for future settings without schema changes

### Implementation Details

**Database**: 
- `TenantSettings` model with one-to-one relationship to `Tenant`
- Alembic migration: `6edffb133c83_create_tenant_settings_table.py`

**API Endpoints**:
- `GET /api/v1/tenants/{id}/settings` - Retrieve settings
- `PUT /api/v1/tenants/{id}/settings` - Update settings
- `POST /api/v1/tenants/{id}/settings/logo` - Upload company logo
- `DELETE /api/v1/tenants/{id}/settings/logo` - Remove logo

**Services**: Settings service with CRUD operations, file upload validation, and default settings initialization

### Future Microservice Split Consideration

**Settings Service Candidate**: The settings functionality is designed as a prime candidate for extraction during the planned microservice split:

**Reasons for Future Split**:
1. **Clear Boundaries**: Settings have minimal dependencies on other business logic
2. **Independent Scaling**: UI customization features may have different load patterns
3. **Team Ownership**: Frontend/UX teams could own settings service independently
4. **Feature Growth**: Settings will likely expand significantly (themes, advanced customization, multi-language support)

**Proposed Settings Service** (Future):
- Port: 8004
- Responsibilities: All tenant customization, branding, UI preferences, themes
- Storage: Settings database + file storage for assets (logos, themes)
- Dependencies: Minimal - only needs tenant validation from Auth Server

**Migration Path**: Settings functionality is already well-isolated with its own models, services, and API endpoints, making extraction straightforward when the time comes.

### Updated Architecture Vision

**Final Target Architecture**:
1. **Spring Authorization Server (9000)**: Identity, tenants, users, RBAC
2. **Content & Ingestion Service (8002)**: Documents, websites, vectors, widgets
3. **Billing & Subscription Service (8003)**: Plans, payments, usage, billing
4. **Settings Service (8004)**: Tenant customization, branding, UI preferences *(Future)*

The settings system provides a clear template for how to design features that can be easily extracted into microservices as the system grows.