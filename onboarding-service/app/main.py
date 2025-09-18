import time
import uuid
import os
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

# Load environment variables at startup
from dotenv import load_dotenv
load_dotenv()

from .api.documents import router as documents_router
from .api.website_ingestions import router as website_ingestions_router
from .api.plans import router as plans_router
from .api.widgets import router as widgets_router
from .api.payments import router as payments_router
from .api.subscriptions import router as subscriptions_router
from .api.logos import router as logos_router
from .api.categorization import router as categorization_router
from .core.config import settings
from .core.logging_config import (
    setup_logging, 
    get_logger, 
    set_request_context, 
    clear_request_context,
    generate_request_id,
    log_api_request,
    log_api_response
)

# Setup structured logging with configuration
setup_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    json_logs=(os.environ.get("ENVIRONMENT", "development").lower() == "production")
)
logger = get_logger("main")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    """Validate environment configuration on startup"""
    logger.info("Starting Onboarding Service...")
    
    # Check critical environment variables
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY environment variable is not set!")
        logger.error("Please add OPENAI_API_KEY to your .env file")
    else:
        logger.info("OPENAI_API_KEY found - vector ingestion enabled")
    
    logger.info("Onboarding Service startup completed")


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for request/response logging and context tracking."""
    start_time = time.time()
    
    # Generate request ID
    request_id = generate_request_id()
    
    # Extract tenant info from headers or path
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")
    
    # Set request context
    set_request_context(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id
    )
    
    # Log request
    log_api_request(
        method=request.method,
        path=str(request.url.path),
        tenant_id=tenant_id,
        user_agent=request.headers.get("user-agent"),
        client_ip=request.client.host if request.client else None
    )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response
        log_api_response(
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms
        )
        
        # Add request ID to response headers
        response.headers["x-request-id"] = request_id
        
        return response
        
    except Exception as e:
        # Calculate duration for error case
        duration_ms = (time.time() - start_time) * 1000
        
        # Log error
        logger.error(
            "Request failed",
            method=request.method,
            path=str(request.url.path),
            duration_ms=duration_ms,
            error=str(e),
            exc_info=True
        )
        
        raise
    finally:
        # Clear request context
        clear_request_context()


# CORS is now handled by the Spring Cloud Gateway
# No need for CORS middleware in the backend service

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include routers
app.include_router(documents_router, prefix=settings.API_V1_STR, tags=["documents"])
app.include_router(website_ingestions_router, prefix=settings.API_V1_STR, tags=["website-ingestions"])
app.include_router(plans_router, prefix=settings.API_V1_STR, tags=["plans"])
app.include_router(widgets_router, prefix=settings.API_V1_STR, tags=["chat-widgets"])
app.include_router(payments_router, prefix=settings.API_V1_STR, tags=["payments"])
app.include_router(subscriptions_router, prefix=settings.API_V1_STR, tags=["subscriptions"])
app.include_router(logos_router, prefix=settings.API_V1_STR, tags=["logos"])
app.include_router(categorization_router, prefix=settings.API_V1_STR, tags=["categorization"])


@app.get("/")
async def root():
    return {"message": "Onboarding Service API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "onboarding-service"}


@app.get("/api/v1/public/info")
async def get_public_info():
    """Get public information about the service for dashboards"""
    return {
        "service": "ChatCraft Onboarding API",
        "version": "1.0.0",
        "status": "operational",
        "features": [
            "Multi-tenant AI chat platform",
            "Document upload and processing",
            "Website scraping and ingestion", 
            "Real-time chat widgets",
            "Subscription plan management",
            "Bearer token authentication",
            "WebSocket chat connections"
        ],
        "available_endpoints": {
            "public": {
                "plans": "/api/v1/plans/public",
                "tenant_signup": "/api/v1/tenants/",
                "login": "http://localhost:9002/auth/oauth2/authorize (OAuth2 flow)",
                "service_info": "/api/v1/public/info",
                "plan_management_ui": "/plan-management"
            },
            "authenticated": {
                "documents": "/api/v1/documents/",
                "websites": "/api/v1/websites/",
                "chat_widgets": "/api/v1/widget/",
                "plans_management": "/api/v1/plans/",
                "plan_switching": "/api/v1/tenants/{id}/switch-plan"
            }
        },
        "authentication": {
            "method": "OAuth 2.0 Bearer Token",
            "required_for": "All endpoints except public ones",
            "authorization_server": "http://localhost:9002/auth"
        },
        "cors": {
            "note": "CORS is handled by the API Gateway",
            "enabled": False,
            "reason": "Prevents duplicate CORS headers"
        }
    }


@app.get("/plan-management")
async def serve_plan_management():
    """Serve the plan management UI"""
    from fastapi.responses import FileResponse
    import os
    
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    plan_management_path = os.path.join(static_dir, "plan-management.html")
    
    if os.path.exists(plan_management_path):
        return FileResponse(plan_management_path, media_type="text/html")
    else:
        raise HTTPException(
            status_code=404, 
            detail="Plan management UI not found"
        )


@app.get("/payment")
async def serve_payment_page():
    """Serve the payment integration UI"""
    from fastapi.responses import FileResponse
    import os
    
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    payment_page_path = os.path.join(static_dir, "payment-integration.html")
    
    if os.path.exists(payment_page_path):
        return FileResponse(payment_page_path, media_type="text/html")
    else:
        raise HTTPException(
            status_code=404, 
            detail="Payment page not found"
        )