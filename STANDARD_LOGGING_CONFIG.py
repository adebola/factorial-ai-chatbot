"""
Standard Logging Configuration for ChatCraft FastAPI Services
==============================================================

This is the standardized logging configuration to be used across ALL FastAPI services.

Features:
- Uses ONLY Loguru (no Structlog)
- Human-readable output (NOT JSON)
- Colored logs in development, plain text in production
- Properly configures third-party library loggers
- Respects LOG_LEVEL environment variable

Usage:
------
Copy this configuration to each service's app/core/logging_config.py
Customize the third-party library list based on service dependencies
"""

import os
import sys
import logging
from loguru import logger


def setup_logging():
    """Configure logging for the service"""

    # Remove default loguru handler
    logger.remove()

    # Get environment and log level
    environment = os.environ.get("ENVIRONMENT", "development")
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # ============================================================================
    # 1. Configure Python's standard logging module
    # ============================================================================
    # This is CRITICAL for third-party libraries that use logging.getLogger()
    # Without this, libraries like uvicorn, aio-pika, sqlalchemy will output
    # DEBUG logs regardless of LOG_LEVEL setting

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing configuration
    )

    # ============================================================================
    # 2. Configure third-party library loggers
    # ============================================================================
    # Set specific log levels for noisy libraries
    # Customize this list based on your service's dependencies

    # Web server (all services use this)
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Access logs too verbose
    logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level, logging.INFO))

    # RabbitMQ libraries (if service uses aio-pika)
    logging.getLogger("aio_pika").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("aiormq").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("pamqp").setLevel(getattr(logging, log_level, logging.INFO))

    # Database libraries (if service uses SQLAlchemy)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # Query logs too verbose
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # HTTP clients (if service uses httpx/urllib3)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Scheduler (if service uses APScheduler)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # AI/ML libraries (if service uses these)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Storage libraries (if service uses MinIO)
    logging.getLogger("minio").setLevel(logging.WARNING)

    # WebSocket libraries (if service uses websockets)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    # ============================================================================
    # 3. Configure Loguru
    # ============================================================================

    if environment == "production":
        # Production: Plain text logs (human-readable, NOT JSON)
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            colorize=False,  # No colors in production
            serialize=False,  # Plain text, NOT JSON
            enqueue=True
        )
    else:
        # Development: Colored logs (human-readable)
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=log_level,
            colorize=True,
            enqueue=True
        )

    logger.info(f"Logging configured - Environment: {environment}, Level: {log_level}")


def get_logger(name: str):
    """
    Get a logger instance for a module

    Usage:
        from app.core.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")
    """
    return logger.bind(module=name)


# ============================================================================
# Helper functions for common logging patterns
# ============================================================================

def log_api_request(method: str, path: str, **kwargs):
    """Log an API request"""
    logger.info(f"API Request: {method} {path}", **kwargs)


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log an API response"""
    logger.info(
        f"API Response: {method} {path} - {status_code} ({duration_ms:.2f}ms)",
        **kwargs
    )


def log_error(error_type: str, error_message: str, **kwargs):
    """Log an error with context"""
    logger.error(f"{error_type}: {error_message}", **kwargs)


def log_tenant_operation(tenant_id: str, operation: str, **kwargs):
    """Log a tenant-specific operation"""
    logger.info(f"Tenant {tenant_id}: {operation}", **kwargs)


# ============================================================================
# Service-Specific Helper Functions
# ============================================================================
# Add service-specific helper functions below
# Examples:

def log_chat_message(tenant_id: str, session_id: str, message_id: str, **kwargs):
    """Log a chat message (for chat-service)"""
    logger.info(
        f"Chat message",
        tenant_id=tenant_id,
        session_id=session_id,
        message_id=message_id,
        **kwargs
    )


def log_document_upload(tenant_id: str, document_id: str, filename: str, **kwargs):
    """Log document upload (for onboarding-service)"""
    logger.info(
        f"Document uploaded: {filename}",
        tenant_id=tenant_id,
        document_id=document_id,
        **kwargs
    )


def log_payment_processed(tenant_id: str, payment_id: str, amount: float, **kwargs):
    """Log payment processing (for billing-service)"""
    logger.info(
        f"Payment processed: {amount}",
        tenant_id=tenant_id,
        payment_id=payment_id,
        **kwargs
    )


def log_email_sent(to_email: str, subject: str, **kwargs):
    """Log email sent (for communications-service)"""
    logger.info(
        f"Email sent to {to_email}: {subject}",
        **kwargs
    )


# ============================================================================
# DO NOT initialize logging on import - let main.py handle it
# ============================================================================