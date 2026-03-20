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
from loguru import logger


def setup_logging():
    """Configure logging for the service using Loguru only"""

    # Remove default loguru handler
    logger.remove()

    # Get environment and log level
    environment = os.environ.get("ENVIRONMENT", "development")
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

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
    # Web server
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Too verbose
    logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level, logging.INFO))

    # Database
    sqlalchemy_log_level = os.environ.get("SQLALCHEMY_LOG_LEVEL", "WARNING")
    logging.getLogger("sqlalchemy.engine").setLevel(sqlalchemy_log_level)
    logging.getLogger("sqlalchemy.pool").setLevel(sqlalchemy_log_level)
    logging.getLogger("sqlalchemy.dialects").setLevel(sqlalchemy_log_level)
    logging.getLogger("sqlalchemy.orm").setLevel(sqlalchemy_log_level)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # HTTP clients
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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


def get_logger(name: str):
    """Get a logger instance"""
    return logger.bind(module=name)


# ============================================================================
# Context Management (Simplified with Loguru)
# ============================================================================

def set_request_context(**context):
    """
    Helper to create a logger with request context.
    Returns a logger bound with the provided context.
    """
    return logger.bind(**context)


def get_request_context():
    """Get current request context (no-op for Loguru, kept for compatibility)"""
    return {}


def clear_request_context():
    """Clear request context from logger (no-op for Loguru, kept for compatibility)"""
    pass


def generate_request_id():
    """Generate a unique request ID."""
    import uuid
    return str(uuid.uuid4())[:8]


# ============================================================================
# Observability-specific logging helpers
# ============================================================================

def log_agent_execution(
    tenant_id: str,
    query_id: str,
    tool_name: str = None,
    duration_ms: float = None,
    error: str = None,
    **kwargs
):
    """Log an agent tool execution"""
    if error:
        logger.error(
            "Agent tool failed",
            tenant_id=tenant_id,
            query_id=query_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            error=error,
            **kwargs
        )
    else:
        logger.info(
            "Agent tool executed",
            tenant_id=tenant_id,
            query_id=query_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            **kwargs
        )


def log_agent_query(
    tenant_id: str,
    query_id: str,
    message_preview: str = None,
    tool_count: int = None,
    total_duration_ms: float = None,
    status: str = None,
    **kwargs
):
    """Log an agent query completion"""
    logger.info(
        "Agent query",
        tenant_id=tenant_id,
        query_id=query_id,
        message_preview=message_preview[:100] if message_preview and len(message_preview) > 100 else message_preview,
        tool_count=tool_count,
        total_duration_ms=total_duration_ms,
        status=status,
        **kwargs
    )


def log_backend_operation(
    operation: str,
    tenant_id: str,
    backend_type: str = None,
    **kwargs
):
    """Log backend configuration operations"""
    logger.info(
        "Backend operation",
        operation=operation,
        tenant_id=tenant_id,
        backend_type=backend_type,
        **kwargs
    )


def log_api_request(
    method: str,
    path: str,
    tenant_id: str = None,
    user_id: str = None,
    **kwargs
):
    """Log API request"""
    logger.info(
        "API request",
        method=method,
        path=path,
        tenant_id=tenant_id,
        user_id=user_id,
        **kwargs
    )


def log_api_response(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **kwargs
):
    """Log API response"""
    logger.info(
        "API response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_tenant_operation(
    operation: str,
    tenant_id: str,
    tenant_name: str = None,
    **kwargs
):
    """Log tenant-specific operations"""
    logger.info(
        "Tenant operation",
        operation=operation,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        **kwargs
    )
