"""
Standardized logging configuration using Loguru only.

Provides:
- Human-readable logs (colored in dev, plain text in production)
- Multi-tenant context via Loguru's .bind() method
- Third-party library log level control
- Simple, maintainable configuration
"""

import os
import sys
import logging
import uuid
from loguru import logger


def setup_logging(
    log_level: str = None,
    json_logs: bool = None,
    log_file: str = None
) -> None:
    """
    Configure logging for the service using Loguru only

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_logs: Ignored - always uses human-readable format
        log_file: Optional log file path
    """

    # Remove default loguru handler
    logger.remove()

    # Auto-detect environment if not specified
    if log_level is None:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    environment = os.environ.get("ENVIRONMENT", "development")

    # ============================================================================
    # 1. Configure Python's standard logging module
    # ============================================================================
    # This is CRITICAL for third-party libraries that use logging.getLogger()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing configuration
    )

    # ============================================================================
    # 2. Configure third-party library loggers
    # ============================================================================
    # Web server (all services)
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Too verbose
    logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level, logging.INFO))

    # RabbitMQ consumer
    logging.getLogger("aio_pika").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("aiormq").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("pamqp").setLevel(getattr(logging, log_level, logging.INFO))

    # Database
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # Background scheduler
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # HTTP clients (Paystack integration)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # ============================================================================
    # 3. Configure Loguru (HUMAN-READABLE output)
    # ============================================================================
    if environment == "production":
        # Production: Plain text logs (human-readable, NOT JSON)
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}{exception}",
            level=log_level,
            colorize=False,  # No colors in production
            serialize=False,  # Plain text, NOT JSON
            enqueue=True
        )
    else:
        # Development: Colored logs (human-readable)
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level> | <blue>{extra}</blue>{exception}",
            level=log_level,
            colorize=True,
            enqueue=True
        )

    logger.info(f"Logging configured - Environment: {environment}, Level: {log_level}")


def get_logger(name: str = None):
    """Get a logger instance"""
    return logger.bind(module=name or "billing-service")


# ============================================================================
# Context Management (Simplified with Loguru)
# ============================================================================

def set_request_context(request_id: str = None, tenant_id: str = None, user_id: str = None):
    """
    Helper to create a logger with request context.
    Returns a logger bound with the provided context.
    """
    context = {}
    if request_id:
        context["request_id"] = request_id
    if tenant_id:
        context["tenant_id"] = tenant_id
    if user_id:
        context["user_id"] = user_id

    return logger.bind(**context)


def clear_request_context():
    """Clear all request context variables (no-op for Loguru, kept for compatibility)"""
    pass


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())


# ============================================================================
# Helper functions for common logging patterns
# ============================================================================

def log_api_request(method: str, path: str, tenant_id: str = None, **kwargs):
    """Log an API request"""
    if path == "/health":
        return

    logger.info(
        "API request",
        method=method,
        path=path,
        tenant_id=tenant_id,
        **kwargs
    )


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log an API response"""
    if path == "/health":
        return

    logger.info(
        "API response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_tenant_operation(operation: str, tenant_id: str, **kwargs):
    """Log a tenant-specific operation"""
    logger.info(
        "Tenant operation",
        operation=operation,
        tenant_id=tenant_id,
        **kwargs
    )


def log_document_processing(action: str, document_id: str, tenant_id: str, **kwargs):
    """Log document processing events"""
    logger.info(
        "Document processing",
        action=action,
        document_id=document_id,
        tenant_id=tenant_id,
        **kwargs
    )


def log_vector_operation(operation: str, tenant_id: str, collection_name: str = None, **kwargs):
    """Log vector store operations"""
    logger.info(
        "Vector operation",
        operation=operation,
        tenant_id=tenant_id,
        collection_name=collection_name,
        **kwargs
    )
