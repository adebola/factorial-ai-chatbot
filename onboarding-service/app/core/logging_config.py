"""
Structured logging configuration for FactorialBot Onboarding Service.

This module sets up structured logging using Loguru + Structlog for:
- Multi-tenant context tracking
- Request ID correlation 
- Structured JSON output for production
- Beautiful console output for development
"""

import os
import sys
import uuid
from typing import Any, Dict, Optional
from contextvars import ContextVar

import structlog
from loguru import logger

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)


# Removed StructlogInterceptHandler to avoid recursion issues


def add_context_processor(logger, method_name, event_dict):
    """Add context variables to log events."""
    if request_id := request_id_var.get():
        event_dict["request_id"] = request_id
    if tenant_id := tenant_id_var.get():
        event_dict["tenant_id"] = tenant_id
    if user_id := user_id_var.get():
        event_dict["user_id"] = user_id
    
    # Add service identifier
    event_dict["service"] = "onboarding-service"
    
    return event_dict


def setup_logging(
    log_level: str = None,
    json_logs: bool = None,
    log_file: Optional[str] = None
) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_logs: Whether to output JSON logs (auto-detected if None)
        log_file: Optional log file path
    """
    # Auto-detect environment if not specified
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    if json_logs is None:
        # Use JSON logs in production (when not in development)
        json_logs = os.getenv("ENVIRONMENT", "development").lower() != "development"
    
    # Set up stdlib logging first
    import logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(name)s - %(levelname)s - %(message)s"
    )
    
    # Configure structlog  
    if json_logs:
        # Production: JSON logs
        processors = [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_context_processor,
            structlog.processors.JSONRenderer()
        ]
    else:
        # Development: Pretty console logs
        processors = [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_context_processor,
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_request_context(request_id: str = None, tenant_id: str = None, user_id: str = None):
    """Set context variables for the current request."""
    if request_id:
        request_id_var.set(request_id)
    if tenant_id:
        tenant_id_var.set(tenant_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context():
    """Clear all request context variables."""
    request_id_var.set(None)
    tenant_id_var.set(None)
    user_id_var.set(None)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


# Helper functions for common logging patterns
def log_api_request(method: str, path: str, tenant_id: str = None, **kwargs):
    """Log an API request."""
    logger = get_logger("api")
    logger.info(
        "API request",
        method=method,
        path=path,
        tenant_id=tenant_id,
        **kwargs
    )


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log an API response."""
    logger = get_logger("api")
    logger.info(
        "API response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_tenant_operation(operation: str, tenant_id: str, **kwargs):
    """Log a tenant-specific operation."""
    logger = get_logger("tenant")
    logger.info(
        "Tenant operation",
        operation=operation,
        tenant_id=tenant_id,
        **kwargs
    )


def log_document_processing(action: str, document_id: str, tenant_id: str, **kwargs):
    """Log document processing events."""
    logger = get_logger("documents")
    logger.info(
        "Document processing",
        action=action,
        document_id=document_id,
        tenant_id=tenant_id,
        **kwargs
    )


def log_vector_operation(operation: str, tenant_id: str, collection_name: str = None, **kwargs):
    """Log vector store operations."""
    logger = get_logger("vectors")
    logger.info(
        "Vector operation",
        operation=operation,
        tenant_id=tenant_id,
        collection_name=collection_name,
        **kwargs
    )