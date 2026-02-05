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
    # Web server (all services)
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Too verbose
    logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level, logging.INFO))

    # RabbitMQ
    logging.getLogger("aio_pika").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("aiormq").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("pamqp").setLevel(getattr(logging, log_level, logging.INFO))

    # Database
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # Scheduler
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

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

def set_request_context(request_id: str = None, tenant_id: str = None, user_id: str = None, session_id: str = None):
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
    if session_id:
        context["session_id"] = session_id

    return logger.bind(**context)


# ============================================================================
# Helper functions for common logging patterns
# ============================================================================

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
