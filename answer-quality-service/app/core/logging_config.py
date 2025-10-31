"""
Structured logging configuration using Loguru and Structlog.

Provides:
- Multi-tenant context (tenant_id, request_id, user_id, session_id)
- Request tracking with unique IDs
- Performance monitoring (timing for operations)
- Environment-based output (pretty console for dev, JSON for production)
"""

import sys
import logging
from contextvars import ContextVar
from typing import Optional, Dict, Any
from loguru import logger
import structlog
from app.core.config import settings

# Context variables for request tracking
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


def configure_logging():
    """Configure Loguru and Structlog for the application"""

    # Remove default Loguru handler
    logger.remove()

    # Add appropriate handler based on environment
    if settings.ENVIRONMENT == "production":
        # Production: JSON format for log aggregation
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {extra} | {message}",
            level=settings.LOG_LEVEL,
            serialize=True,  # JSON output
        )
    else:
        # Development: Pretty console format
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level> | {extra}",
            level=settings.LOG_LEVEL,
            colorize=True,
        )

    # Silence verbose third-party loggers in production
    if settings.ENVIRONMENT == "production":
        # SQLAlchemy loggers - reduce noise from SQL queries and connection pool
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)

        # Other potentially verbose loggers
        logging.getLogger("alembic").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.ENVIRONMENT == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Get a logger instance for a module"""
    return logger.bind(module=name, service=settings.SERVICE_NAME)


def set_request_context(
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
):
    """
    Set request context for logging.

    All subsequent log messages will include these values.

    Usage:
        set_request_context(
            request_id="req-123",
            tenant_id="tenant-456",
            user_id="user-789"
        )
    """
    context = request_context.get().copy()

    if request_id:
        context["request_id"] = request_id
    if tenant_id:
        context["tenant_id"] = tenant_id
    if user_id:
        context["user_id"] = user_id
    if session_id:
        context["session_id"] = session_id

    context.update(kwargs)
    request_context.set(context)

    # Bind to structlog
    structlog.contextvars.bind_contextvars(**context)


def clear_request_context():
    """Clear request context"""
    request_context.set({})
    structlog.contextvars.clear_contextvars()


def get_request_context() -> Dict[str, Any]:
    """Get current request context"""
    return request_context.get()


# Logging helper functions

def log_api_request(method: str, path: str, **kwargs):
    """Log API request"""
    logger.info(
        f"API Request: {method} {path}",
        method=method,
        path=path,
        **kwargs
    )


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log API response"""
    logger.info(
        f"API Response: {method} {path} - {status_code}",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_feedback_submission(
    tenant_id: str,
    message_id: str,
    feedback_type: str,
    has_comment: bool = False
):
    """Log feedback submission"""
    logger.info(
        "Feedback submitted",
        event_type="feedback_submitted",
        tenant_id=tenant_id,
        message_id=message_id,
        feedback_type=feedback_type,
        has_comment=has_comment
    )


def log_quality_analysis(
    tenant_id: str,
    message_id: str,
    retrieval_score: float,
    answer_confidence: float,
    duration_ms: float
):
    """Log quality analysis operation"""
    logger.info(
        "Quality analysis completed",
        event_type="quality_analysis",
        tenant_id=tenant_id,
        message_id=message_id,
        retrieval_score=retrieval_score,
        answer_confidence=answer_confidence,
        duration_ms=duration_ms
    )


def log_knowledge_gap_detected(
    tenant_id: str,
    gap_id: str,
    pattern: str,
    occurrence_count: int
):
    """Log knowledge gap detection"""
    logger.info(
        "Knowledge gap detected",
        event_type="knowledge_gap_detected",
        tenant_id=tenant_id,
        gap_id=gap_id,
        pattern=pattern,
        occurrence_count=occurrence_count
    )


def log_tenant_operation(operation: str, tenant_id: str, **kwargs):
    """Log tenant-specific operation"""
    logger.info(
        f"Tenant operation: {operation}",
        operation=operation,
        tenant_id=tenant_id,
        **kwargs
    )


# Initialize logging on module import
configure_logging()
