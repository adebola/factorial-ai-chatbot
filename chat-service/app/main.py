import time
import os
from fastapi import FastAPI, Request

# Load environment variables at startup
from dotenv import load_dotenv
load_dotenv()

from .api.chat import router as chat_router
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
from .services.limit_warning_consumer import limit_warning_consumer
from .services.event_publisher import event_publisher
from .services.rabbitmq_diagnostics import log_diagnostics

# Setup structured logging with configuration
setup_logging(
    log_level=os.environ.get('LOG_LEVEL', 'INFO'),
    json_logs=(os.environ.get('ENVIRONMENT', 'development').lower() == "production")
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

    # Start RabbitMQ limit warning consumer
    consumer_started = False
    try:
        limit_warning_consumer.start()
        consumer_started = True
        logger.info("✓ Limit warning consumer initialization started (running in background thread)")
    except Exception as e:
        logger.error(f"Failed to start limit warning consumer: {e}", exc_info=True)
        logger.warning("Chat service will continue without limit warning consumer")
        # Run diagnostics to help identify the issue
        logger.info("Running RabbitMQ connection diagnostics...")
        log_diagnostics()

    # Connect event publisher
    publisher_connected = False
    try:
        event_publisher.connect()
        publisher_connected = True
        logger.info("✓ Event publisher connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect event publisher: {e}", exc_info=True)
        logger.warning("Chat service will continue without event publisher")
        # Run diagnostics to help identify the issue (only if not already run)
        logger.info("Running RabbitMQ connection diagnostics...")
        log_diagnostics()

    # Log RabbitMQ connection summary
    rabbitmq_status = {
        "event_publisher": "connected" if publisher_connected else "disconnected",
        "limit_warning_consumer": "started" if consumer_started else "not_started"
    }
    logger.info(
        f"RabbitMQ Integration Status: "
        f"Publisher={rabbitmq_status['event_publisher']}, "
        f"Consumer={rabbitmq_status['limit_warning_consumer']}",
        extra=rabbitmq_status
    )

    logger.info("Chat Service startup completed")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down Chat Service...")

    # Stop limit warning consumer
    try:
        limit_warning_consumer.stop()
        logger.info("Limit warning consumer stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping limit warning consumer: {e}", exc_info=True)

    # Close event publisher
    try:
        event_publisher.close()
        logger.info("Event publisher closed successfully")
    except Exception as e:
        logger.error(f"Error closing event publisher: {e}", exc_info=True)

    logger.info("Chat Service shutdown completed")


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for request/response logging and context tracking."""
    # Skip middleware for WebSocket connections
    if request.url.path.startswith("/ws/"):
        return await call_next(request)

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
app.include_router(admin_chat_router, prefix=f"{settings.API_V1_STR}/chat", tags=["admin", "chat"])

# Also include WebSocket route at root level for easier client access
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "Chat Service API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "chat-service"}