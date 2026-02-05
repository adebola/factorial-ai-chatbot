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
        stream=sys.stdout,
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
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # AI/ML libraries
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # WebSocket connections
    logging.getLogger("websockets").setLevel(logging.WARNING)

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
    return logger.bind(module=name or "chat-service")


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


def clear_request_context():
    """Clear all request context variables (no-op for Loguru, kept for compatibility)"""
    pass


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())


# ============================================================================
# Helper functions for common logging patterns
# ============================================================================

def log_websocket_connection(action: str, tenant_id: str = None, session_id: str = None, **kwargs):
    """Log WebSocket connection events"""
    logger.info(
        "WebSocket connection",
        action=action,
        tenant_id=tenant_id,
        session_id=session_id,
        **kwargs
    )


def log_chat_message(direction: str, tenant_id: str, session_id: str, message_length: int = None, **kwargs):
    """Log chat message events"""
    logger.info(
        "Chat message",
        direction=direction,  # "incoming" or "outgoing"
        tenant_id=tenant_id,
        session_id=session_id,
        message_length=message_length,
        **kwargs
    )


def log_ai_generation(tenant_id: str, session_id: str, duration_ms: float, token_count: int = None, **kwargs):
    """Log AI response generation"""
    logger.info(
        "AI generation",
        tenant_id=tenant_id,
        session_id=session_id,
        duration_ms=duration_ms,
        token_count=token_count,
        **kwargs
    )


def log_vector_search(tenant_id: str, query_length: int, results_count: int, duration_ms: float, **kwargs):
    """Log vector search operations"""
    logger.info(
        "Vector search",
        tenant_id=tenant_id,
        query_length=query_length,
        results_count=results_count,
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


def log_api_request(method: str, path: str, tenant_id: str = None, user_agent: str = None, client_ip: str = None, **kwargs):
    """Log API request events"""
    if path == "/health":
        return

    logger.info(
        "API request",
        method=method,
        path=path,
        tenant_id=tenant_id,
        user_agent=user_agent,
        client_ip=client_ip,
        **kwargs
    )


def log_api_response(method: str, path: str, status_code: int, duration_ms: float, **kwargs):
    """Log API response events"""
    logger.info(
        "API response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )
