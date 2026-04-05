"""Audit Service — Centralized audit event storage and query API."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .core.database import engine
from .core.telemetry import setup_telemetry
from .api.audit import router as audit_router
from .services.audit_consumer import audit_consumer

setup_logging()
logger = get_logger("audit-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Audit Service...")

    # Start RabbitMQ audit event consumer
    try:
        await audit_consumer.connect()
        await audit_consumer.start_consuming()
        logger.info("Audit event consumer started successfully")
    except Exception as e:
        logger.error(f"Failed to start audit consumer: {e}")
        logger.warning("Service will continue but audit events will not be consumed")

    # Start retention scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from .services.retention_service import run_retention_cleanup

        scheduler = BackgroundScheduler()
        scheduler.add_job(run_retention_cleanup, 'cron', hour=2, minute=0)
        scheduler.start()
        logger.info("Retention scheduler started (daily at 2am)")
    except Exception as e:
        logger.error(f"Failed to start retention scheduler: {e}")

    logger.info("Audit Service startup completed")
    yield

    # Shutdown
    logger.info("Shutting down Audit Service...")
    try:
        await audit_consumer.stop()
    except Exception as e:
        logger.error(f"Error stopping audit consumer: {e}")

    logger.info("Audit Service shutdown completed")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Centralized audit event storage and compliance query API",
    lifespan=lifespan,
)

# OpenTelemetry instrumentation
setup_telemetry(app, service_name="audit-service", engine=engine)

# Routers
app.include_router(audit_router, prefix=f"{settings.API_V1_STR}/audit", tags=["audit"])


@app.get("/")
async def root():
    return {"service": "Audit Service", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "audit-service"}
