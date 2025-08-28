import time
import os
from fastapi import FastAPI, Request

# Load environment variables at startup
from dotenv import load_dotenv
load_dotenv()

from .api.chat import router as chat_router
from .api.vectors import router as vectors_router
from .api.admin_chat import router as admin_chat_router
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
    log_level=os.environ['LOG_LEVEL'],
    json_logs=(os.environ['ENVIRONMENT'].lower() == "production")
)
logger = get_logger("main")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    """Validate environment configuration on startup"""
    logger.info("Starting Chat Service...")
    
    # Check critical environment variables
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.error("OPENAI_API_KEY environment variable is not set!")
        logger.error("Please add OPENAI_API_KEY to your .env file")
    else:
        logger.info("OPENAI_API_KEY found - AI chat enabled")

    
    logger.info("Chat Service startup completed")


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for request/response logging and context tracking."""
    start_time = time.time()
    
    # Generate request ID
    request_id = generate_request_id()
    
    # Extract tenant info from headers or path
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")
    session_id = request.headers.get("x-session-id")
    
    # Set request context
    set_request_context(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id
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

# Include routers
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(vectors_router, prefix=f"{settings.API_V1_STR}/vectors", tags=["vectors"])
app.include_router(admin_chat_router, prefix=f"{settings.API_V1_STR}/chat", tags=["admin", "chat"])

# Also include WebSocket route at root level for easier client access
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "Chat Service API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "chat-service"}