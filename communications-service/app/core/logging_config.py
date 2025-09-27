import os
import sys
import json
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from loguru import logger


def setup_logging():
    """Configure structured logging for the communications service"""

    # Remove default loguru handler
    logger.remove()

    # Get environment and log level
    environment = os.environ.get("ENVIRONMENT", "development")
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    if environment == "production":
        # Production: JSON structured logs
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
            level=log_level,
            serialize=True,  # Output as JSON
            enqueue=True
        )
    else:
        # Development: Pretty colored logs
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=log_level,
            colorize=True,
            enqueue=True
        )

    # Map log levels to integers for structlog
    log_level_map = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50
    }

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer() if environment == "production" else structlog.dev.ConsoleRenderer(colors=True)
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level_map.get(log_level, 20)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


# Request context storage
_request_context: Dict[str, Any] = {}


def set_request_context(**kwargs):
    """Set context that will be included in all logs for this request"""
    global _request_context
    _request_context.update(kwargs)


def clear_request_context():
    """Clear the request context"""
    global _request_context
    _request_context.clear()


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger with request context"""
    base_logger = structlog.get_logger(name)
    return base_logger.bind(**_request_context)


# Helper functions for common logging patterns
def log_message_sent(
    message_type: str,
    message_id: str,
    tenant_id: str,
    recipient: str,
    provider: str,
    **kwargs
):
    """Log when a message is sent"""
    logger_instance = get_logger("message_delivery")
    logger_instance.info(
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
    logger_instance = get_logger("message_delivery")
    logger_instance.error(
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
    logger_instance = get_logger("template_usage")
    logger_instance.info(
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
    logger_instance = get_logger("rate_limiting")
    logger_instance.warning(
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
    payload: Dict,
    **kwargs
):
    """Log incoming webhooks"""
    logger_instance = get_logger("webhooks")
    logger_instance.info(
        "Webhook received",
        provider=provider,
        event_type=event_type,
        message_id=message_id,
        payload_keys=list(payload.keys()),
        **kwargs
    )


# Don't initialize logging on import - let main.py handle it