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
    PluginManifest,
    RegisterByUrlRequest,
    UiExtensionEntry,
)
from ..services.audit_publisher import audit_publisher
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
        icon_url=service.icon_url,
        capabilities=service.capabilities,
        ui_hints=service.ui_hints,
        ui_extensions=service.ui_extensions,
        health_status=service.health_status,
        last_manifest_fetch_at=service.last_manifest_fetch_at,
        last_health_at=service.last_health_at,
        is_active=service.is_active,
        tenant_count=tenant_count,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


async def _fetch_manifest(base_url: str, manifest_path: str = "/manifest") -> PluginManifest:
    """Call the plugin's manifest endpoint and validate the response.

    Raises HTTPException(502) on any failure — the catalog cannot register a
    plugin whose manifest cannot be fetched and parsed.
    """
    url = base_url.rstrip("/") + "/" + manifest_path.lstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach plugin manifest at {url}: {e}",
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plugin manifest at {url} returned HTTP {resp.status_code}",
        )
    try:
        return PluginManifest(**resp.json())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plugin manifest at {url} is invalid: {e}",
        )


def _apply_manifest(service: AgenticService, manifest: PluginManifest) -> None:
    """Persist a freshly-fetched manifest onto a catalog row."""
    service.manifest = manifest.dict()
    service.ui_extensions = [ext.dict() for ext in manifest.ui_extensions]
    service.capabilities = manifest.capabilities
    service.last_manifest_fetch_at = datetime.now(timezone.utc)
    # Manifest fields override stale catalog metadata.
    service.name = manifest.name
    service.service_key = manifest.service_key
    service.category = manifest.category
    if manifest.description:
        service.description = manifest.description


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
        icon_url=request.icon_url,
        capabilities=request.capabilities,
        ui_hints=request.ui_hints,
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


# NOTE: literal-segment routes (`/services/ui-extensions`, `/services/register-by-url`)
# MUST be declared before any `/services/{service_id}` routes — FastAPI matches in
# declaration order, so a parametrized route would otherwise swallow the literal.
@router.get("/services/ui-extensions", response_model=List[UiExtensionEntry])
async def list_ui_extensions(
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Flat list of UI extensions contributed by all installed, active plugins.

    The superadmin shell calls this on bootstrap to render dynamic menu entries.
    Filters: `is_active=true`, `is_deleted=false`. Health status is included so
    the UI can grey out menu items for unhealthy plugins (we don't hide them
    here — that's a UI policy decision).

    Role filtering: entries whose `required_role` is more restrictive than the
    caller's role are dropped. Currently this endpoint requires SYSTEM_ADMIN
    via the dependency, so all role buckets are visible.
    """
    services = db.query(AgenticService).filter(
        AgenticService.is_active == True,
        AgenticService.is_deleted == False,
    ).all()

    entries: List[UiExtensionEntry] = []
    for svc in services:
        if not svc.ui_extensions:
            continue
        for ext in svc.ui_extensions:
            try:
                entries.append(UiExtensionEntry(
                    service_id=svc.id,
                    service_key=svc.service_key,
                    service_name=svc.name,
                    menu_label=ext.get("menu_label"),
                    icon=ext.get("icon"),
                    route=ext.get("route"),
                    required_role=ext.get("required_role", "SUPER_ADMIN"),
                    api_prefix=ext.get("api_prefix"),
                    health_status=svc.health_status,
                ))
            except Exception as e:
                logger.warning(
                    f"Skipping malformed ui_extension on service "
                    f"'{svc.service_key}': {e}"
                )
    return entries


@router.post(
    "/services/register-by-url",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_service_by_url(
    request: RegisterByUrlRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Convenience: provide a base_url, the catalog fetches /manifest and registers.

    If a service with the manifest's `service_key` already exists, the existing
    row is updated in place (idempotent re-registration).
    """
    manifest = await _fetch_manifest(request.base_url, request.manifest_path)

    existing = db.query(AgenticService).filter(
        AgenticService.service_key == manifest.service_key,
        AgenticService.is_deleted == False,
    ).first()

    if existing:
        existing.base_url = request.base_url
        if request.health_check_url:
            existing.health_check_url = request.health_check_url
        _apply_manifest(existing, manifest)
        db.commit()
        db.refresh(existing)
        logger.info(f"Service '{existing.service_key}' re-registered by {claims.email}")
        return _service_to_response(existing, db)

    service = AgenticService(
        name=manifest.name,
        service_key=manifest.service_key,
        description=manifest.description,
        base_url=request.base_url,
        health_check_url=request.health_check_url,
        category=manifest.category,
    )
    _apply_manifest(service, manifest)
    db.add(service)
    db.commit()
    db.refresh(service)
    logger.info(f"Service '{service.service_key}' registered by {claims.email} via manifest")
    return _service_to_response(service, db)


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
    """Perform a health check on a service.

    Persists the result onto the catalog row (`health_status` + `last_health_at`)
    so the dynamic UI-extensions endpoint can filter on it without re-probing.
    """
    service = _get_active_service(service_id, db)

    url = service.health_check_url or (service.base_url.rstrip("/") + "/health" if service.base_url else None)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service has no health check URL or base URL configured",
        )

    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            import time
            start = time.time()
            resp = await client.get(url)
            latency_ms = round((time.time() - start) * 1000, 2)
        new_status = "healthy" if resp.status_code < 400 else "unhealthy"
        service.health_status = new_status
        service.last_health_at = now
        db.commit()
        return {
            "status": new_status,
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "url": url,
        }
    except httpx.RequestError as e:
        service.health_status = "unhealthy"
        service.last_health_at = now
        db.commit()
        return {
            "status": "unreachable",
            "error": str(e),
            "url": url,
        }


# `refresh-manifest` is parametrized so it can live alongside the other
# `/services/{service_id}/...` routes below — it does not collide with the
# literal endpoints because the discriminator is the trailing literal segment.
@router.post("/services/{service_id}/refresh-manifest", response_model=ServiceResponse)
async def refresh_service_manifest(
    service_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Re-fetch the plugin's GET /manifest and persist it onto the catalog row."""
    service = _get_active_service(service_id, db)
    if not service.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service has no base_url configured",
        )

    manifest = await _fetch_manifest(service.base_url)
    _apply_manifest(service, manifest)
    db.commit()
    db.refresh(service)
    logger.info(f"Manifest refreshed for service '{service.service_key}' by {claims.email}")
    return _service_to_response(service, db)


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
        try:
            await audit_publisher.publish(
                action_type="service.assigned",
                tier="data",
                source_service="billing-service",
                tenant_id=request.tenant_id,
                actor_user_id=claims.user_id,
                actor_email=claims.email,
                resource_type="tenant_service_assignment",
                resource_id=existing.id,
                after_state={"service_key": service.service_key, "reactivated": True},
            )
        except Exception:
            pass
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
    try:
        await audit_publisher.publish(
            action_type="service.assigned",
            tier="data",
            source_service="billing-service",
            tenant_id=request.tenant_id,
            actor_user_id=claims.user_id,
            actor_email=claims.email,
            resource_type="tenant_service_assignment",
            resource_id=assignment.id,
            after_state={"service_key": service.service_key, "reactivated": False},
        )
    except Exception:
        pass
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
    try:
        await audit_publisher.publish(
            action_type="service.revoked",
            tier="data",
            source_service="billing-service",
            tenant_id=tenant_id,
            actor_user_id=claims.user_id,
            actor_email=claims.email,
            resource_type="tenant_service_assignment",
            resource_id=assignment.id,
            after_state={"service_key": service.service_key, "is_active": False},
        )
    except Exception:
        pass


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
