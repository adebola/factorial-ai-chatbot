"""
Answer Quality & Feedback Service - Main Application

FastAPI microservice for measuring and improving RAG chatbot answer quality.
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.api import health, feedback, quality, admin, alerts
from app.services.rabbitmq_consumer import rabbitmq_consumer
from app.services.scheduler import background_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for the application.
    Runs on startup and shutdown.
    """
    # Configure logging FIRST
    setup_logging()

    # THEN get logger instance
    logger = get_logger(__name__)

    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'configured'}")
    logger.info(f"Auth Server: {settings.AUTH_SERVER_URL}")

    # Start RabbitMQ consumer for processing chat messages (aio-pika)
    try:
        await rabbitmq_consumer.start_consuming()
        logger.info("✓ RabbitMQ consumer started successfully (aio-pika)")
    except Exception as e:
        logger.exception(f"Failed to start RabbitMQ consumer: {e}")
        logger.warning("Service will continue without RabbitMQ consumer")

    # Start background scheduler for periodic jobs
    try:
        background_scheduler.start()
        logger.info("Background scheduler started successfully")
    except Exception as e:
        logger.exception(f"Failed to start background scheduler: {e}")
        logger.warning("Service will continue without background scheduler")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.SERVICE_NAME}")

    # Stop background scheduler
    try:
        background_scheduler.stop()
        logger.info("Background scheduler stopped successfully")
    except Exception as e:
        logger.exception(f"Error stopping background scheduler: {e}")

    # Stop RabbitMQ consumer
    try:
        await rabbitmq_consumer.close()
        logger.info("RabbitMQ consumer stopped successfully")
    except Exception as e:
        logger.exception(f"Error stopping RabbitMQ consumer: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.SERVICE_NAME,
    description="Answer Quality & Feedback Service for RAG Chatbot",
    version="1.0.0",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # Configure appropriately for production
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Include routers
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["health"])
app.include_router(feedback.router, prefix=f"{settings.API_V1_STR}/feedback", tags=["feedback"])
app.include_router(quality.router, prefix=f"{settings.API_V1_STR}/quality", tags=["quality"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(alerts.router, prefix=f"{settings.API_V1_STR}/alerts", tags=["alerts"])

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.SERVICE_NAME,
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENVIRONMENT,
        "docs": f"{settings.API_V1_STR}/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower()
    )
