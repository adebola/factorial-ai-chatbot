"""
Billing Service - Main Application Entry Point

Manages subscription plans, billing, and payment processing for ChatCraft tenants.
"""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import time

# Load environment variables from .env file FIRST
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from .core.config import settings
from .core.database import engine, Base
from .core.logging_config import setup_logging, get_logger
from .api import plans, subscriptions, payments, usage
from .services.usage_consumer import usage_consumer

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

    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")

    # Start RabbitMQ usage event consumer
    try:
        logger.info("Connecting to RabbitMQ for usage events...")
        usage_consumer.connect()
        usage_consumer.start_consuming()
        logger.info("Usage event consumer started successfully")
    except Exception as e:
        logger.error(f"Failed to start usage event consumer: {e}")
        logger.warning("Service will continue but usage events will not be processed")

    yield

    # Shutdown
    logger.info("Shutting down Billing Service...")

    # Stop usage event consumer
    try:
        usage_consumer.stop_consuming()
        logger.info("Usage event consumer stopped")
    except Exception as e:
        logger.error(f"Error stopping usage event consumer: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Billing and subscription management service for ChatCraft",
    lifespan=lifespan
)

# CORS is handled by the gateway service - no need to configure it here
# If running billing service standalone (without gateway), uncomment below:
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


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
    prefix=settings.API_V1_STR,
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
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
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
