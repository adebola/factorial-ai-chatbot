# Production Widget Deployment Guide

## Issue Resolution

The chat widget was hardcoded to use localhost URLs (`ws://localhost:8000/ws/chat` and `http://localhost:8001/static/chatcraft-logo2.png`) which caused failures in production.

## Solution Implemented

### 1. Environment-Based URL Generation

The widget service now detects the environment and generates appropriate URLs:

**Development Environment:**
- Backend URL: `http://localhost:8001`
- Chat Service URL: `http://localhost:8000`
- WebSocket URL: `ws://localhost:8000/ws/chat`
- Logo URL: `http://localhost:8001/api/v1/widget/static/chatcraft-logo2.png`

**Production Environment:**
- Backend URL: `https://api.chatcraft.cc`
- Chat Service URL: `https://api.chatcraft.cc`
- WebSocket URL: `wss://api.chatcraft.cc/ws/chat`
- Logo URL: `https://api.chatcraft.cc/api/v1/widget/static/chatcraft-logo2.png`

### 2. Static Asset Serving

Created a new endpoint `/api/v1/widget/static/{filename}` to serve widget assets:
- Serves logo files securely with whitelisting
- Proper content-type headers
- Caching headers for performance
- Routes through the existing API gateway configuration

### 3. Environment Configuration

The widget service now reads these environment variables:

```env
# Required for production
ENVIRONMENT=production
PRODUCTION_DOMAIN=api.chatcraft.cc

# Optional - fallbacks to localhost in development
BACKEND_URL=http://localhost:8001
CHAT_SERVICE_URL=http://localhost:8000
```

## Production Deployment Steps

### 1. Update Environment Variables

In your production environment, ensure these variables are set:

```env
ENVIRONMENT=production
PRODUCTION_DOMAIN=api.chatcraft.cc
```

### 2. Verify Widget Generation

After deployment, test widget generation:

```bash
# Generate a widget for a tenant
curl -X GET "https://api.chatcraft.cc/api/v1/widget/generate" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Download the generated JavaScript
curl -X GET "https://api.chatcraft.cc/api/v1/widget/chat-widget.js" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Verify URLs in the JavaScript file
grep -E "(backend_url|chat_service_url|wss://)" downloaded-widget.js
```

### 3. Test Static Asset Access

Verify the logo loads correctly:

```bash
curl -X GET "https://api.chatcraft.cc/api/v1/widget/static/chatcraft-logo2.png" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Code Changes Made

### 1. Widget Service (`app/services/widget_service.py`)

```python
# Environment detection and URL generation
environment = os.getenv("ENVIRONMENT", "development").lower()
production_domain = os.getenv("PRODUCTION_DOMAIN", "api.chatcraft.cc")

if environment == "production" or environment == "prod":
    backend_url = f"https://{production_domain}"
    chat_service_url = f"https://{production_domain}"
else:
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8001")
    chat_service_url = os.getenv("CHAT_SERVICE_URL", "http://localhost:8000")
```

### 2. Widget API (`app/api/widgets.py`)

```python
@router.get("/widget/static/{filename}")
async def get_widget_static_asset(filename: str):
    """Serve static assets for the chat widget"""
    # Security: whitelist allowed files
    # Proper content-type headers
    # Cache control for performance
```

### 3. JavaScript Template Updates

```javascript
// WebSocket URL conversion with environment awareness
let wsUrl = CONFIG.chatServiceUrl.replace('http://', 'ws://').replace('https://', 'wss://');
const wsEndpoint = `${wsUrl}/ws/chat?api_key=${CONFIG.apiKey}`;

// Logo URL routed through API gateway
<img src="{{ backend_url }}/api/v1/widget/static/chatcraft-logo2.png" alt="ChatCraft" class="factorial-chat-logo">
```

## Expected Production Widget URLs

When `ENVIRONMENT=production`, the generated widget will contain:

```javascript
const CONFIG = {
    backendUrl: 'https://api.chatcraft.cc',
    chatServiceUrl: 'https://api.chatcraft.cc',
    // ... other config
};

// WebSocket connection will use:
// wss://api.chatcraft.cc/ws/chat?api_key=...

// Logo will load from:
// https://api.chatcraft.cc/api/v1/widget/static/chatcraft-logo2.png
```

## Testing

### Manual Testing

1. Set production environment variables
2. Generate a widget via the API
3. Inspect the generated JavaScript for correct URLs
4. Test the widget on a webpage
5. Verify WebSocket connection and logo loading

### Automated Testing

Run the test script to verify URL generation:

```bash
cd onboarding-service
python test_widget_urls.py
```

## Troubleshooting

### Widget Still Using Localhost URLs

**Cause:** Environment variables not set correctly

**Solution:**
```bash
# Check current environment
echo $ENVIRONMENT

# Set for production
export ENVIRONMENT=production
export PRODUCTION_DOMAIN=api.chatcraft.cc

# Restart the service
```

### Logo Not Loading

**Cause:** Static asset endpoint not accessible

**Solution:**
1. Verify the file exists: `onboarding-service/static/chatcraft-logo2.png`
2. Test the endpoint: `GET /api/v1/widget/static/chatcraft-logo2.png`
3. Check nginx routing for `/api/v1/` paths

### WebSocket Connection Failed

**Cause:** WebSocket URL not properly converted

**Solution:**
1. Verify nginx WebSocket configuration at `/ws/chat`
2. Check that `wss://` protocol is used in production
3. Ensure chat service is accessible from nginx proxy

## Benefits

1. **Environment Awareness**: Automatic URL generation based on deployment environment
2. **Security**: Whitelisted static asset serving
3. **Performance**: Proper caching headers for static assets
4. **Maintainability**: Centralized URL configuration
5. **Production Ready**: No hardcoded localhost URLs

## Future Enhancements

1. **CDN Support**: Add CDN URL configuration for static assets
2. **Multi-Domain Support**: Support multiple production domains
3. **Custom Logo Upload**: Allow tenants to upload custom logos
4. **Widget Analytics**: Track widget loading and usage
5. **A/B Testing**: Support different widget configurations per tenant