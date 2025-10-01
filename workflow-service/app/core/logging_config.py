import os
import sys
import json
from contextvars import ContextVar
from typing import Dict, Any, Optional
from loguru import logger
import structlog

# Context variables for request tracking
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})

def setup_logging():
    """Setup structured logging with Loguru + Structlog"""

    # Remove default handler
    logger.remove()

    # Determine log level
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    environment = os.environ.get("ENVIRONMENT", "development")

    if environment == "development":
        # Pretty console logging for development
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>workflow-service</cyan> | "
                   "<level>{message}</level>",
            level=log_level,
            colorize=True
        )
    else:
        # JSON logging for production
        logger.add(
            sys.stderr,
            format="{message}",
            level=log_level,
            serialize=True
        )

    # Configure structlog with simpler configuration
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer() if environment == "production" else structlog.dev.ConsoleRenderer()
        ],
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str):
    """Get a logger with the given name"""
    return structlog.get_logger(name)

def set_request_context(**context):
    """Set context variables for the current request"""
    current = request_context.get({})
    current.update(context)
    request_context.set(current)

def get_request_context() -> Dict[str, Any]:
    """Get current request context"""
    return request_context.get({})

# Workflow-specific logging helpers
def log_workflow_execution(
    workflow_id: str,
    session_id: str,
    tenant_id: str,
    step_id: Optional[str] = None,
    **kwargs
):
    """Log workflow execution events"""
    logger.info(
        "Workflow execution",
        workflow_id=workflow_id,
        session_id=session_id,
        tenant_id=tenant_id,
        step_id=step_id,
        **kwargs
    )

def log_workflow_trigger(
    tenant_id: str,
    trigger_type: str,
    message: str,
    triggered: bool,
    **kwargs
):
    """Log workflow trigger events"""
    logger.info(
        "Workflow trigger evaluation",
        tenant_id=tenant_id,
        trigger_type=trigger_type,
        message_preview=message[:100] if len(message) > 100 else message,
        triggered=triggered,
        **kwargs
    )

def log_workflow_state_change(
    workflow_id: str,
    session_id: str,
    from_step: Optional[str],
    to_step: str,
    **kwargs
):
    """Log workflow state changes"""
    logger.info(
        "Workflow state change",
        workflow_id=workflow_id,
        session_id=session_id,
        from_step=from_step,
        to_step=to_step,
        **kwargs
    )

def log_api_request(
    method: str,
    path: str,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
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
    tenant_name: Optional[str] = None,
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