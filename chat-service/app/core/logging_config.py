"""
Structured logging configuration for FactorialBot Chat Service.

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
session_id_var: ContextVar[Optional[str]] = ContextVar('session_id', default=None)


# Removed StructlogInterceptHandler to avoid recursion issues


def add_context_processor(logger, method_name, event_dict):
    """Add context variables to log events."""
    if request_id := request_id_var.get():
        event_dict["request_id"] = request_id
    if tenant_id := tenant_id_var.get():
        event_dict["tenant_id"] = tenant_id
    if user_id := user_id_var.get():
        event_dict["user_id"] = user_id
    if session_id := session_id_var.get():
        event_dict["session_id"] = session_id
    
    # Add service identifier
    event_dict["service"] = "chat-service"
    
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
    
    # Remove default Loguru logger
    logger.remove()
    
    # Configure structlog
    if json_logs:
        # Production: JSON logs
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_context_processor,
            structlog.processors.JSONRenderer()
        ]
        
        # Console output for production
        logger.add(
            sys.stdout,
            format="{message}",
            level=log_level,
            serialize=True,  # JSON output
            backtrace=True,
            diagnose=True
        )
    else:
        # Development: Simple console logs with structlog context
        def custom_formatter(logger, name, event_dict):
            """Custom formatter that includes structured context"""
            level = event_dict.get("level", "info").upper()
            message = event_dict.get("event", "")
            
            # Build context string
            context_parts = []
            for key, value in event_dict.items():
                if key not in ["level", "event", "timestamp", "logger"]:
                    context_parts.append(f"{key}={value}")
            
            context_str = " ".join(context_parts)
            if context_str:
                return f"[{level}] {message} | {context_str}"
            return f"[{level}] {message}"
        
        processors = [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_context_processor,
            custom_formatter
        ]
        
        # Pretty console output for development with all levels
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
            level=log_level.upper(),
            colorize=True,
            backtrace=True,
            diagnose=True
        )
    
    # Optional file logging
    if log_file:
        logger.add(
            log_file,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level>",
            level=log_level,
            rotation="100 MB",
            retention="30 days",
            compression="gz"
        )
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set the root logger level to ensure all levels pass through
    import logging
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))
    
    # Don't intercept standard library logging to avoid recursion
    # Let uvicorn and fastapi use their default logging
    pass


def get_logger(name: str = None):
    """Get a structured logger instance."""
    # For development, use loguru directly to ensure all levels work
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "development":
        from loguru import logger as loguru_logger
        
        # Create a custom logger wrapper that adds context
        class ContextualLogger:
            def __init__(self, name=None):
                self.name = name or "app"
                
            def _log_with_context(self, level, message, **kwargs):
                # Get context variables
                context = {}
                if request_id := request_id_var.get():
                    context["request_id"] = request_id
                if tenant_id := tenant_id_var.get():
                    context["tenant_id"] = tenant_id
                if user_id := user_id_var.get():
                    context["user_id"] = user_id
                if session_id := session_id_var.get():
                    context["session_id"] = session_id
                
                context["service"] = "chat-service"
                context.update(kwargs)
                
                # Format context as string
                if context:
                    context_str = " | " + " ".join(f"{k}={v}" for k, v in context.items())
                    full_message = f"{message}{context_str}"
                else:
                    full_message = message
                
                # Use loguru to log with the appropriate level
                getattr(loguru_logger, level.lower())(full_message)
            
            def debug(self, message, **kwargs):
                self._log_with_context("DEBUG", message, **kwargs)
                
            def info(self, message, **kwargs):
                self._log_with_context("INFO", message, **kwargs)
                
            def warning(self, message, **kwargs):
                self._log_with_context("WARNING", message, **kwargs)
                
            def error(self, message, **kwargs):
                self._log_with_context("ERROR", message, **kwargs)
                
            def critical(self, message, **kwargs):
                self._log_with_context("CRITICAL", message, **kwargs)
        
        return ContextualLogger(name)
    else:
        # Production: use structlog
        return structlog.get_logger(name)


def set_request_context(request_id: str = None, tenant_id: str = None, user_id: str = None, session_id: str = None):
    """Set context variables for the current request."""
    if request_id:
        request_id_var.set(request_id)
    if tenant_id:
        tenant_id_var.set(tenant_id)
    if user_id:
        user_id_var.set(user_id)
    if session_id:
        session_id_var.set(session_id)


def clear_request_context():
    """Clear all request context variables."""
    request_id_var.set(None)
    tenant_id_var.set(None)
    user_id_var.set(None)
    session_id_var.set(None)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


# Helper functions for common logging patterns
def log_websocket_connection(action: str, tenant_id: str = None, session_id: str = None, **kwargs):
    """Log WebSocket connection events."""
    get_logger("websocket").info(
        "WebSocket connection",
        action=action,
        tenant_id=tenant_id,
        session_id=session_id,
        **kwargs
    )


def log_chat_message(direction: str, tenant_id: str, session_id: str, message_length: int = None, **kwargs):
    """Log chat message events."""
    get_logger("chat").info(
        "Chat message",
        direction=direction,  # "incoming" or "outgoing"
        tenant_id=tenant_id,
        session_id=session_id,
        message_length=message_length,
        **kwargs
    )


def log_ai_generation(tenant_id: str, session_id: str, duration_ms: float, token_count: int = None, **kwargs):
    """Log AI response generation."""
    get_logger("ai").info(
        "AI generation",
        tenant_id=tenant_id,
        session_id=session_id,
        duration_ms=duration_ms,
        token_count=token_count,
        **kwargs
    )


def log_vector_search(tenant_id: str, query_length: int, results_count: int, duration_ms: float, **kwargs):
    """Log vector search operations."""
    get_logger("vectors").info(
        "Vector search",
        tenant_id=tenant_id,
        query_length=query_length,
        results_count=results_count,
        duration_ms=duration_ms,
        **kwargs
    )


def log_tenant_operation(operation: str, tenant_id: str, **kwargs):
    """Log a tenant-specific operation."""
    get_logger("tenant").info(
        "Tenant operation",
        operation=operation,
        tenant_id=tenant_id,
        **kwargs
    )


def log_api_request(method: str, path: str, tenant_id: str = None, user_agent: str = None, client_ip: str = None, **kwargs):
    """Log API request events."""

    if path == "/health":
        return

    get_logger("api").info(
        "API request",
        method=method,
        path=path,
        tenant_id=tenant_id,
        user_agent=user_agent,
        client_ip=client_ip,
        **kwargs
    )


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log API response events."""
    logger = get_logger("api")
    logger.info(
        "API response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )