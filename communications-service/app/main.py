from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .api import email, sms
from .services.rabbitmq_consumer import RabbitMQConsumer
import threading
import time


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Communications Service", version="1.0.0")

    # Start RabbitMQ consumer in a separate thread
    consumer = RabbitMQConsumer()
    consumer_thread = threading.Thread(target=start_rabbitmq_consumer, args=(consumer, logger))
    consumer_thread.daemon = True
    consumer_thread.start()
    logger.info("Started RabbitMQ consumer thread")

    yield

    logger.info("Shutting down Communications Service")
    # Consumer will be stopped automatically when the main thread exits


def start_rabbitmq_consumer(consumer: RabbitMQConsumer, logger):
    """Start RabbitMQ consumer with retry logic"""
    max_retries = 5
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            logger.info(f"Starting RabbitMQ consumer (attempt {attempt + 1}/{max_retries})")
            consumer.start_consuming()
            break
        except Exception as e:
            logger.error(f"Failed to start RabbitMQ consumer (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Failed to start RabbitMQ consumer after all retries")
                # Don't crash the whole service, just log the error


def create_app() -> FastAPI:
    # Setup logging first
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Communications microservice for sending emails and SMS",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan
    )

    # CORS is now handled by the Spring Cloud Gateway
    # No need for CORS middleware in the backend service

    # Include routers
    app.include_router(
        email.router,
        prefix=f"{settings.API_V1_STR}/email",
        tags=["email"]
    )

    app.include_router(
        sms.router,
        prefix=f"{settings.API_V1_STR}/sms",
        tags=["sms"]
    )

    @app.get("/")
    async def root():
        return {
            "message": "Communications Service",
            "version": "1.0.0",
            "status": "running"
        }

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "communications-service",
            "version": "1.0.0"
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True
    )