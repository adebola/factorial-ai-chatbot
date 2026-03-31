"""
Admin CRUD endpoints for the Agentic Service Registry.

All endpoints require SYSTEM_ADMIN role.
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.agentic_service import AgenticService, TenantServiceAssignment
from ..schemas.agentic_service import (
    ServiceCreateRequest,
    ServiceUpdateRequest,
    ServiceResponse,
    AssignRequest,
    AssignmentUpdateRequest,
    AssignmentResponse,
    TenantServiceResponse,
)
from ..services.dependencies import TokenClaims, require_system_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──

def _service_to_response(service: AgenticService, db: Session) -> ServiceResponse:
    tenant_count = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.service_id == service.id,
        TenantServiceAssignment.is_active == True,
    ).count()
    return ServiceResponse(
        id=service.id,
        name=service.name,
        service_key=service.service_key,
        description=service.description,
        base_url=service.base_url,
        health_check_url=service.health_check_url,
        category=service.category,
        is_active=service.is_active,
        tenant_count=tenant_count,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


def _get_active_service(service_id: str, db: Session) -> AgenticService:
    service = db.query(AgenticService).filter(
        AgenticService.id == service_id,
        AgenticService.is_deleted == False,
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


# ── Invalidate Redis cache for a tenant+service ──

def _invalidate_service_cache(tenant_id: str, service_key: str):
    """Best-effort invalidation of the Redis access cache."""
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(redis_url)
        cache_key = f"svc_access:{tenant_id}:{service_key}"
        r.delete(cache_key)
        logger.info(f"Invalidated cache key {cache_key}")
    except Exception as e:
        logger.warning(f"Failed to invalidate cache: {e}")


# ═══════════════════════════════════════════════════════════
# SERVICE CATALOG CRUD
# ═══════════════════════════════════════════════════════════

@router.post("/services", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    request: ServiceCreateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Register a new agentic service in the catalog."""
    existing = db.query(AgenticService).filter(
        (AgenticService.service_key == request.service_key) |
        (AgenticService.name == request.name),
        AgenticService.is_deleted == False,
    ).first()
    if existing:
        field = "service_key" if existing.service_key == request.service_key else "name"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service with this {field} already exists",
        )

    service = AgenticService(
        name=request.name,
        service_key=request.service_key,
        description=request.description,
        base_url=request.base_url,
        health_check_url=request.health_check_url,
        category=request.category,
    )
    db.add(service)
    db.commit()
    db.refresh(service)

    logger.info(f"Service '{service.service_key}' created by {claims.email}")
    return _service_to_response(service, db)


@router.get("/services", response_model=List[ServiceResponse])
async def list_services(
    include_inactive: bool = False,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List all registered agentic services."""
    query = db.query(AgenticService).filter(AgenticService.is_deleted == False)
    if not include_inactive:
        query = query.filter(AgenticService.is_active == True)
    services = query.order_by(AgenticService.name).all()
    return [_service_to_response(s, db) for s in services]


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get details of a specific service."""
    service = _get_active_service(service_id, db)
    return _service_to_response(service, db)


@router.put("/services/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: str,
    request: ServiceUpdateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Update a service's metadata."""
    service = _get_active_service(service_id, db)

    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    logger.info(f"Service '{service.service_key}' updated by {claims.email}")
    return _service_to_response(service, db)


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Soft-delete a service."""
    service = _get_active_service(service_id, db)
    service.is_deleted = True
    service.is_active = False
    service.deleted_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Service '{service.service_key}' soft-deleted by {claims.email}")


@router.get("/services/{service_id}/health")
async def health_check_service(
    service_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Perform a health check on a service."""
    service = _get_active_service(service_id, db)

    url = service.health_check_url or (service.base_url.rstrip("/") + "/health" if service.base_url else None)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service has no health check URL or base URL configured",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            import time
            start = time.time()
            resp = await client.get(url)
            latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "status": "healthy" if resp.status_code < 400 else "unhealthy",
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "url": url,
        }
    except httpx.RequestError as e:
        return {
            "status": "unreachable",
            "error": str(e),
            "url": url,
        }


# ═══════════════════════════════════════════════════════════
# TENANT ASSIGNMENT CRUD
# ═══════════════════════════════════════════════════════════

@router.post("/services/{service_id}/assign", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_service_to_tenant(
    service_id: str,
    request: AssignRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Assign a service to a tenant."""
    service = _get_active_service(service_id, db)

    existing = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.tenant_id == request.tenant_id,
        TenantServiceAssignment.service_id == service_id,
    ).first()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Service already assigned to this tenant",
            )
        # Re-activate
        existing.is_active = True
        existing.config = request.config
        existing.notes = request.notes
        existing.assigned_by = claims.user_id
        existing.assigned_by_email = claims.email
        existing.deactivated_at = None
        existing.deactivated_by = None
        db.commit()
        db.refresh(existing)
        _invalidate_service_cache(request.tenant_id, service.service_key)
        logger.info(f"Service '{service.service_key}' re-assigned to tenant {request.tenant_id} by {claims.email}")
        return AssignmentResponse.from_orm(existing)

    assignment = TenantServiceAssignment(
        tenant_id=request.tenant_id,
        service_id=service_id,
        assigned_by=claims.user_id,
        assigned_by_email=claims.email,
        config=request.config,
        notes=request.notes,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _invalidate_service_cache(request.tenant_id, service.service_key)
    logger.info(f"Service '{service.service_key}' assigned to tenant {request.tenant_id} by {claims.email}")
    return AssignmentResponse.from_orm(assignment)


@router.delete("/services/{service_id}/assign/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_service_from_tenant(
    service_id: str,
    tenant_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Revoke a service from a tenant."""
    service = _get_active_service(service_id, db)

    assignment = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.tenant_id == tenant_id,
        TenantServiceAssignment.service_id == service_id,
        TenantServiceAssignment.is_active == True,
    ).first()

    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    assignment.is_active = False
    assignment.deactivated_at = datetime.now(timezone.utc)
    assignment.deactivated_by = claims.user_id
    db.commit()

    _invalidate_service_cache(tenant_id, service.service_key)
    logger.info(f"Service '{service.service_key}' revoked from tenant {tenant_id} by {claims.email}")


@router.put("/services/{service_id}/assign/{tenant_id}", response_model=AssignmentResponse)
async def update_assignment(
    service_id: str,
    tenant_id: str,
    request: AssignmentUpdateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Update a tenant's service assignment (config, notes, active status)."""
    service = _get_active_service(service_id, db)

    assignment = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.tenant_id == tenant_id,
        TenantServiceAssignment.service_id == service_id,
    ).first()

    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    update_data = request.dict(exclude_unset=True)

    if "is_active" in update_data:
        if not update_data["is_active"] and assignment.is_active:
            assignment.deactivated_at = datetime.now(timezone.utc)
            assignment.deactivated_by = claims.user_id
        elif update_data["is_active"] and not assignment.is_active:
            assignment.deactivated_at = None
            assignment.deactivated_by = None

    for field, value in update_data.items():
        setattr(assignment, field, value)

    db.commit()
    db.refresh(assignment)

    _invalidate_service_cache(tenant_id, service.service_key)
    logger.info(f"Assignment for service '{service.service_key}' / tenant {tenant_id} updated by {claims.email}")
    return AssignmentResponse.from_orm(assignment)


@router.get("/services/{service_id}/tenants", response_model=List[AssignmentResponse])
async def list_assigned_tenants(
    service_id: str,
    include_inactive: bool = False,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List all tenants assigned to a service."""
    _get_active_service(service_id, db)

    query = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.service_id == service_id
    )
    if not include_inactive:
        query = query.filter(TenantServiceAssignment.is_active == True)

    assignments = query.order_by(TenantServiceAssignment.created_at.desc()).all()
    return [AssignmentResponse.from_orm(a) for a in assignments]


@router.get("/tenants/{tenant_id}/services", response_model=List[ServiceResponse])
async def list_tenant_services(
    tenant_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List all services assigned to a tenant (admin view)."""
    assignments = db.query(TenantServiceAssignment).filter(
        TenantServiceAssignment.tenant_id == tenant_id,
        TenantServiceAssignment.is_active == True,
    ).all()

    service_ids = [a.service_id for a in assignments]
    if not service_ids:
        return []

    services = db.query(AgenticService).filter(
        AgenticService.id.in_(service_ids),
        AgenticService.is_deleted == False,
    ).all()

    return [_service_to_response(s, db) for s in services]
