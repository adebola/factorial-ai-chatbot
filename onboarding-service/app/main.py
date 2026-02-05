import time
import uuid
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

# Load environment variables at startup
from dotenv import load_dotenv
load_dotenv()

from .api.documents import router as documents_router
from .api.website_ingestions import router as website_ingestions_router
from .api.widgets import router as widgets_router
from .api.logos import router as logos_router
from .api.categorization import router as categorization_router
from .api.admin_stats import router as admin_stats_router
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
from .services.jwt_validator import jwt_validator
from .services.usage_publisher import usage_publisher
from .services.rabbitmq_service import rabbitmq_service

# Setup structured logging with configuration
setup_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    json_logs=(os.environ.get("ENVIRONMENT", "development").lower() == "production")
)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events - startup and shutdown"""
    # Startup
    logger.info("Starting Onboarding Service...")

    # Check critical environment variables
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY environment variable is not set!")
        logger.error("Please add OPENAI_API_KEY to your .env file")
    else:
        logger.info("OPENAI_API_KEY found - vector ingestion enabled")

    # Initialize RabbitMQ publishers (aio-pika with automatic reconnection)
    try:
        logger.info("Connecting usage event publisher...")
        await usage_publisher.connect()
        logger.info("✓ Usage event publisher connected successfully")
    except Exception as e:
        logger.exception(
            f"Failed to connect usage publisher: {e}. "
            f"Service will continue but usage events will not be published until RabbitMQ is available.")

    try:
        logger.info("Connecting RabbitMQ service...")
        await rabbitmq_service.connect()
        logger.info("✓ RabbitMQ service connected successfully")
    except Exception as e:
        logger.exception(
            f"Failed to connect RabbitMQ service: {e}. "
            f"Service will continue but plan/logo events may fail to publish.")

    logger.info("Onboarding Service startup completed")

    yield

    # Shutdown
    logger.info("Shutting down Onboarding Service...")

    # Close RabbitMQ publishers (aio-pika)
    try:
        await usage_publisher.close()
        logger.info("Usage event publisher closed")
    except Exception as e:
        logger.error(f"Error closing usage publisher: {e}")

    try:
        await rabbitmq_service.close()
        logger.info("RabbitMQ service closed")
    except Exception as e:
        logger.error(f"Error closing RabbitMQ service: {e}")

    logger.info("Onboarding Service shutdown completed")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for request/response logging and context tracking."""
    start_time = time.time()

    # Generate request ID
    request_id = generate_request_id()

    # Extract tenant info from JWT token
    tenant_id = None
    user_id = None

    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            # Validate and decode JWT token
            payload = await jwt_validator.validate_token(token)
            tenant_id = payload.get("tenant_id")
            user_id = payload.get("user_id") or payload.get("sub")
        except Exception as e:
            # Log but don't fail - some endpoints are public
            logger.debug(f"Could not extract tenant info from token: {e}")

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
            error=str(e))
        
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
app.include_router(widgets_router, prefix=settings.API_V1_STR, tags=["chat-widgets"])
app.include_router(logos_router, prefix=settings.API_V1_STR, tags=["logos"])
app.include_router(categorization_router, prefix=settings.API_V1_STR, tags=["categorization"])
app.include_router(admin_stats_router, prefix=settings.API_V1_STR, tags=["admin"])


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


# Billing-related endpoints have been removed
# Plans, payments, and subscriptions are now handled by the Billing Service