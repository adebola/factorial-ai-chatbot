# Widget API URL Migration Guide

## Overview
This document outlines the URL changes for the widget API endpoints in the onboarding service. The migration removes the `tenant_id` path parameter since it's already available in the JWT token claims.

## Migration Date
- **Date:** 2025-09-10
- **Breaking Change:** Yes
- **Affected Service:** Onboarding Service (Port 8001)

## URL Mapping Table

| Old URL Pattern | New URL Pattern | HTTP Method | Description |
|-----------------|-----------------|-------------|-------------|
| `/api/v1/widgets/{tenant_id}/generate` | `/api/v1/widget/generate` | GET | Generate or regenerate widget files |
| `/api/v1/widgets/{tenant_id}/chat-widget.js` | `/api/v1/widget/chat-widget.js` | GET | Download widget JavaScript file |
| `/api/v1/widgets/{tenant_id}/chat-widget.css` | `/api/v1/widget/chat-widget.css` | GET | Download widget CSS file |
| `/api/v1/widgets/{tenant_id}/chat-widget.html` | `/api/v1/widget/chat-widget.html` | GET | Download widget demo HTML file |
| `/api/v1/widgets/{tenant_id}/integration-guide.html` | `/api/v1/widget/integration-guide.html` | GET | Download integration guide |
| `/api/v1/widgets/{tenant_id}/download-all` | `/api/v1/widget/download-all` | GET | Download all files as ZIP |
| `/api/v1/widgets/{tenant_id}/preview` | `/api/v1/widget/preview` | GET | Preview widget in demo page |
| `/api/v1/widgets/{tenant_id}/status` | `/api/v1/widget/status` | GET | Get widget configuration status |

## Key Changes

### 1. Route Structure
- **Before:** `/api/v1/widgets/{tenant_id}/...`
- **After:** `/api/v1/widget/...`
- **Note:** Changed from plural `widgets` to singular `widget`

### 2. Tenant Identification
- **Before:** Tenant ID passed as path parameter AND validated against JWT token
- **After:** Tenant ID extracted solely from JWT token claims
- **Security:** Enhanced - single source of truth for tenant identification

### 3. Authentication
- **No Change:** Still requires Bearer token in Authorization header
- **Format:** `Authorization: Bearer <token>`
- **Token Claims:** Must contain `tenant_id` and `user_id`

## Angular Service Update Examples

### Before (with tenant_id in path):
```typescript
export class WidgetService {
  private apiUrl = 'http://localhost:8001/api/v1';
  
  generateWidget(tenantId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/widgets/${tenantId}/generate`);
  }
  
  downloadJavaScript(tenantId: string): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/widgets/${tenantId}/chat-widget.js`, 
      { responseType: 'blob' });
  }
  
  getWidgetStatus(tenantId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/widgets/${tenantId}/status`);
  }
}
```

### After (no tenant_id in path):
```typescript
export class WidgetService {
  private apiUrl = 'http://localhost:8001/api/v1';
  
  generateWidget(): Observable<any> {
    return this.http.get(`${this.apiUrl}/widget/generate`);
  }
  
  downloadJavaScript(): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/widget/chat-widget.js`, 
      { responseType: 'blob' });
  }
  
  getWidgetStatus(): Observable<any> {
    return this.http.get(`${this.apiUrl}/widget/status`);
  }
}
```

## Response Format Changes

### Generate Widget Response
The `download_urls` field in the response has been updated:

**Before:**
```json
{
  "download_urls": {
    "javascript": "/api/v1/widgets/{tenant_id}/chat-widget.js",
    "css": "/api/v1/widgets/{tenant_id}/chat-widget.css",
    "demo_html": "/api/v1/widgets/{tenant_id}/chat-widget.html",
    "integration_guide": "/api/v1/widgets/{tenant_id}/integration-guide.html",
    "download_all": "/api/v1/widgets/{tenant_id}/download-all"
  }
}
```

**After:**
```json
{
  "download_urls": {
    "javascript": "/api/v1/widget/chat-widget.js",
    "css": "/api/v1/widget/chat-widget.css",
    "demo_html": "/api/v1/widget/chat-widget.html",
    "integration_guide": "/api/v1/widget/integration-guide.html",
    "download_all": "/api/v1/widget/download-all"
  }
}
```

### Status Endpoint Response
The `download_endpoints` field has been similarly updated to remove tenant_id from all URLs.

## Error Handling

### Removed Validations
The following validation is no longer needed as tenant_id comes from the token:

```python
# This validation has been REMOVED from all endpoints:
if claims.tenant_id != tenant_id:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied"
    )
```

### Common Error Responses
- **401 Unauthorized:** Missing or invalid JWT token
- **403 Forbidden:** Token missing required claims (tenant_id, user_id)
- **500 Internal Server Error:** Widget generation or file operation failed

## Testing the New Endpoints

### Using cURL:
```bash
# Generate widget
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/v1/widget/generate

# Download JavaScript file
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/v1/widget/chat-widget.js \
  -o chat-widget.js

# Get widget status
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/v1/widget/status
```

## Migration Checklist for Angular Application

- [ ] Update all widget service methods to remove `tenantId` parameter
- [ ] Update all API URL constants from `/widgets/` to `/widget/`
- [ ] Remove any client-side tenant ID validation for widget routes
- [ ] Update any hardcoded widget URLs in templates
- [ ] Test all widget operations with the new endpoints
- [ ] Update any API documentation or comments
- [ ] Verify error handling still works correctly

## Rollback Plan

If issues arise, the changes can be reverted by:
1. Restoring the original `/widgets/{tenant_id}/` route structure
2. Re-adding tenant_id validation in each endpoint
3. Updating URL references back to the original format

## Support

For any issues or questions regarding this migration:
- Service: Onboarding Service
- Port: 8001
- Related Services: Authorization Server (Port 9002)