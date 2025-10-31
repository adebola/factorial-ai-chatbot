"""
Health check endpoints for service monitoring.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.core.config import settings
from app.core.logging_config import get_logger
import time
import os

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.

    Returns service status without checking dependencies.
    Useful for container orchestration (Kubernetes liveness probe).
    """
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT
    }


@router.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness check endpoint.

    Checks that the service is ready to handle requests by verifying:
    - Database connectivity
    - Required environment variables

    Useful for container orchestration (Kubernetes readiness probe).

    Returns:
        200 OK if ready, 503 Service Unavailable if not ready
    """
    checks = {
        "service": settings.SERVICE_NAME,
        "status": "ready",
        "checks": {}
    }

    # Check database connectivity
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        db_latency_ms = round((time.time() - start) * 1000, 2)
        checks["checks"]["database"] = {
            "status": "healthy",
            "latency_ms": db_latency_ms
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["status"] = "unhealthy"
        checks["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check required environment variables
    required_env_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "RABBITMQ_HOST",
        "AUTH_SERVER_URL"
    ]

    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        checks["status"] = "unhealthy"
        checks["checks"]["environment"] = {
            "status": "unhealthy",
            "missing_variables": missing_vars
        }
    else:
        checks["checks"]["environment"] = {
            "status": "healthy"
        }

    # Return appropriate status code
    if checks["status"] == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks
        )

    return checks


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check endpoint.

    Returns whether the service is alive (not deadlocked or hanging).
    Simpler than readiness check - only verifies the service is responding.

    Useful for container orchestration (Kubernetes liveness probe).
    """
    return {
        "status": "alive",
        "service": settings.SERVICE_NAME,
        "timestamp": time.time()
    }
