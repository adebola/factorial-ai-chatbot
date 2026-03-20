"""
Backend configuration CRUD API.
"""
import time
import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.backend_config import ObservabilityBackend
from ..schemas.backend import (
    BackendCreateRequest, BackendUpdateRequest, BackendResponse, BackendTestResult
)
from ..services.dependencies import TokenClaims, validate_token, require_admin
from ..services.credential_service import credential_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/backends", response_model=BackendResponse, status_code=201)
async def create_backend(
    request: BackendCreateRequest,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a backend configuration for a tenant."""
    # Only allow admin to configure their own tenant (unless system admin)
    if not claims.is_system_admin and request.tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot configure backends for other tenants"
        )

    # Check for existing backend of same type
    existing = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == request.tenant_id,
        ObservabilityBackend.backend_type == request.backend_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backend type '{request.backend_type}' already configured for this tenant"
        )

    # Encrypt credentials if provided
    encrypted_creds = None
    if request.credentials:
        encrypted_creds = credential_service.encrypt(request.credentials)

    backend = ObservabilityBackend(
        tenant_id=request.tenant_id,
        backend_type=request.backend_type,
        url=request.url,
        auth_type=request.auth_type,
        credentials_encrypted=encrypted_creds,
        verify_ssl=request.verify_ssl,
        timeout_seconds=request.timeout_seconds
    )

    db.add(backend)
    db.commit()
    db.refresh(backend)

    logger.info(f"Created {request.backend_type} backend for tenant {request.tenant_id}")
    return backend


@router.get("/backends", response_model=List[BackendResponse])
async def list_backends(
    tenant_id: str = None,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db)
):
    """List backend configurations for a tenant."""
    target_tenant = tenant_id or claims.tenant_id

    if not claims.is_system_admin and target_tenant != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view backends for other tenants"
        )

    backends = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == target_tenant
    ).all()

    return backends


@router.put("/backends/{tenant_id}/{backend_type}", response_model=BackendResponse)
async def update_backend(
    tenant_id: str,
    backend_type: str,
    request: BackendUpdateRequest,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a backend configuration."""
    if not claims.is_system_admin and tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update backends for other tenants"
        )

    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    if request.url is not None:
        backend.url = request.url
    if request.auth_type is not None:
        backend.auth_type = request.auth_type
    if request.credentials is not None:
        backend.credentials_encrypted = credential_service.encrypt(request.credentials)
    if request.verify_ssl is not None:
        backend.verify_ssl = request.verify_ssl
    if request.timeout_seconds is not None:
        backend.timeout_seconds = request.timeout_seconds
    if request.is_active is not None:
        backend.is_active = request.is_active

    db.commit()
    db.refresh(backend)
    return backend


@router.delete("/backends/{tenant_id}/{backend_type}", status_code=204)
async def delete_backend(
    tenant_id: str,
    backend_type: str,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a backend configuration."""
    if not claims.is_system_admin and tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete backends for other tenants"
        )

    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    db.delete(backend)
    db.commit()


@router.post("/backends/{tenant_id}/{backend_type}/test", response_model=BackendTestResult)
async def test_backend(
    tenant_id: str,
    backend_type: str,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Test connectivity to a backend."""
    if not claims.is_system_admin and tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot test backends for other tenants"
        )

    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    if not backend.url:
        return BackendTestResult(
            backend_type=backend_type,
            url=None,
            reachable=False,
            error="No URL configured"
        )

    # Test connectivity based on backend type
    test_paths = {
        "prometheus": "/api/v1/status/config",
        "alertmanager": "/api/v1/status",
        "elasticsearch": "/",
        "jaeger": "/api/services",
        "otel_collector": "/metrics",
        "llm": None,  # Skip HTTP test for LLM
    }

    test_path = test_paths.get(backend_type, "/health")

    if test_path is None:
        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=True,
            details={"note": "LLM backends are tested on first query"}
        )

    start_time = time.time()
    try:
        # Build auth headers
        headers = {"Content-Type": "application/json"}
        auth = None
        if backend.credentials_encrypted:
            creds = credential_service.decrypt(backend.credentials_encrypted)
            if creds and backend.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {creds.get('token', '')}"
            elif creds and backend.auth_type == "basic":
                auth = (creds.get("username", ""), creds.get("password", ""))

        async with httpx.AsyncClient(verify=backend.verify_ssl, timeout=backend.timeout_seconds) as client:
            response = await client.get(
                f"{backend.url}{test_path}",
                headers=headers,
                auth=auth
            )

        response_time_ms = (time.time() - start_time) * 1000

        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=response.status_code < 500,
            response_time_ms=round(response_time_ms, 1),
            details={"status_code": response.status_code}
        )

    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=str(e)
        )
