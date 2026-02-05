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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Communications Service", version="1.0.0")

    # Start RabbitMQ consumer (aio-pika with automatic reconnection)
    consumer = RabbitMQConsumer()
    try:
        logger.info("Starting RabbitMQ consumer...")
        await consumer.start_consuming()
        logger.info("✓ RabbitMQ consumer started successfully (aio-pika)")
    except Exception as e:
        logger.exception(f"Failed to start RabbitMQ consumer: {e}")
        logger.warning("Service will continue without RabbitMQ consumer")

    yield

    logger.info("Shutting down Communications Service")

    # Stop RabbitMQ consumer
    try:
        await consumer.stop_consuming()
        logger.info("RabbitMQ consumer stopped successfully")
    except Exception as e:
        logger.exception(f"Error stopping RabbitMQ consumer: {e}")


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