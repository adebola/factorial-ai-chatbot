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
    # RabbitMQ consumer
    logging.getLogger("aio_pika").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("aiormq").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("pamqp").setLevel(getattr(logging, log_level, logging.INFO))

    # Web server
    logging.getLogger("uvicorn").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Too verbose
    logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level, logging.INFO))

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

def set_request_context(**kwargs):
    """
    Helper to create a logger with request context.
    Returns a logger bound with the provided context.
    """
    return logger.bind(**kwargs)


def clear_request_context():
    """Clear the request context (no-op for Loguru, kept for compatibility)"""
    pass


# ============================================================================
# Helper functions for common logging patterns
# ============================================================================

def log_message_sent(
    message_type: str,
    message_id: str,
    tenant_id: str,
    recipient: str,
    provider: str,
    **kwargs
):
    """Log when a message is sent"""
    logger.info(
        "Message sent",
        message_type=message_type,
        message_id=message_id,
        tenant_id=tenant_id,
        recipient=recipient,
        provider=provider,
        **kwargs
    )


def log_message_failed(
    message_type: str,
    message_id: str,
    tenant_id: str,
    recipient: str,
    error: str,
    **kwargs
):
    """Log when a message fails"""
    logger.error(
        "Message failed",
        message_type=message_type,
        message_id=message_id,
        tenant_id=tenant_id,
        recipient=recipient,
        error=error,
        **kwargs
    )


def log_template_usage(
    template_id: str,
    template_name: str,
    tenant_id: str,
    message_type: str,
    **kwargs
):
    """Log template usage"""
    logger.info(
        "Template used",
        template_id=template_id,
        template_name=template_name,
        tenant_id=tenant_id,
        message_type=message_type,
        **kwargs
    )


def log_rate_limit_hit(
    tenant_id: str,
    limit_type: str,
    current_count: int,
    limit: int,
    **kwargs
):
    """Log when rate limit is hit"""
    logger.warning(
        "Rate limit exceeded",
        tenant_id=tenant_id,
        limit_type=limit_type,
        current_count=current_count,
        limit=limit,
        **kwargs
    )


def log_webhook_received(
    provider: str,
    event_type: str,
    message_id: str,
    payload: dict,
    **kwargs
):
    """Log incoming webhooks"""
    logger.info(
        "Webhook received",
        provider=provider,
        event_type=event_type,
        message_id=message_id,
        payload_keys=list(payload.keys()),
        **kwargs
    )
