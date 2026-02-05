"""
Billing Service - Main Application Entry Point

Manages subscription plans, billing, and payment processing for ChatCraft tenants.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import time
# Load environment variables from .env file FIRST
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .api import plans, subscriptions, payments, usage, restrictions, plan_management, invoices, analytics, admin
from .services.usage_consumer import usage_consumer
from .messaging.user_consumer import user_consumer
from .services.scheduler import start_scheduler, stop_scheduler

# Setup logging
setup_logging()
logger = get_logger("billing-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Billing Service...")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"API Version: {settings.API_V1_STR}")
    logger.info(f"FrontEnd URL: {os.getenv('FRONTEND_URL', 'http://localhost:3000')}")

    # Note: Database tables are managed by Alembic migrations
    # Run: alembic upgrade head (before starting service)

    # Start RabbitMQ usage event consumer (aio-pika with automatic reconnection)
    try:
        logger.info("Connecting to RabbitMQ for usage events...")
        await usage_consumer.connect()
        await usage_consumer.start_consuming()
        logger.info("Usage event consumer started successfully")
    except Exception as e:
        logger.error(f"Failed to start usage event consumer: {e}")
        logger.warning("Service will continue but usage events will not be processed")

    # Start RabbitMQ user creation event consumer
    try:
        logger.info("Connecting to RabbitMQ for user creation events...")
        await user_consumer.connect()
        await user_consumer.start_consuming()
        logger.info("User creation event consumer started successfully")
    except Exception as e:
        logger.error(f"Failed to start user creation event consumer: {e}")
        logger.warning("Service will continue but user creation events will not be processed")

    # Start background job scheduler
    try:
        logger.info("Starting background job scheduler...")
        start_scheduler()
        logger.info("Background job scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        logger.warning("Service will continue but scheduled jobs will not run")

    yield

    # Shutdown
    logger.info("Shutting down Billing Service...")

    # Stop background job scheduler
    try:
        stop_scheduler()
        logger.info("Background job scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")

    # Stop usage event consumer
    try:
        await usage_consumer.stop_consuming()
        logger.info("Usage event consumer stopped")
    except Exception as e:
        logger.error(f"Error stopping usage event consumer: {e}")

    # Stop user creation event consumer
    try:
        await user_consumer.stop_consuming()
        logger.info("User creation event consumer stopped")
    except Exception as e:
        logger.error(f"Error stopping user creation event consumer: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Billing and subscription management service for ChatCraft",
    lifespan=lifespan
)

# CORS is handled by the gateway service - no need to configure it here

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests"""
    start_time = time.time()

    # Skip logging for health check
    if request.url.path != "/health":
        logger.info(f"Request: {request.method} {request.url.path}")

    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time
    duration_ms = duration * 1000

    # Skip logging for health check
    if request.url.path != "/health":
        logger.info(
            f"Response: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration_ms:.2f}ms"
        )

    return response


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "billing-service",
        "version": "1.0.0"
    }


# Include API routers
app.include_router(
    plans.router,
    prefix=settings.API_V1_STR,
    tags=["plans"]
)

app.include_router(
    subscriptions.router,
    prefix=f"{settings.API_V1_STR}/subscriptions",
    tags=["subscriptions"]
)

app.include_router(
    payments.router,
    prefix=settings.API_V1_STR,
    tags=["payments"]
)

app.include_router(
    usage.router,
    prefix=f"{settings.API_V1_STR}/usage",
    tags=["usage"]
)

app.include_router(
    restrictions.router,
    prefix=f"{settings.API_V1_STR}/restrictions",
    tags=["restrictions"]
)

app.include_router(
    plan_management.router,
    prefix=settings.API_V1_STR,
    tags=["plan-management"]
)

app.include_router(
    invoices.router,
    prefix=f"{settings.API_V1_STR}/invoices",
    tags=["invoices"]
)

app.include_router(
    analytics.router,
    prefix=settings.API_V1_STR,
    tags=["analytics"]
)

app.include_router(
    admin.router,
    prefix=settings.API_V1_STR,
    tags=["admin"]
)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Billing Service",
        "version": "1.0.0",
        "description": "Subscription and payment management for ChatCraft",
        "api_docs": f"{settings.API_V1_STR}/docs"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error": str(exc) if os.getenv("ENVIRONMENT") == "development" else "An error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8004,
        reload=True,
        log_level="info"
    )
