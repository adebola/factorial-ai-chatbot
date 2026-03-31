"""
LLM provider catalog (super-admin) and tenant LLM selection (tenant-admin) routes.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.llm_provider import LLMProvider, TenantLLMSelection
from ..schemas.llm_config import (
    LLMProviderCreateRequest, LLMProviderUpdateRequest, LLMProviderResponse,
    TenantLLMSelectRequest, TenantLLMUpdateRequest, TenantLLMSelectionResponse,
)
from ..services.dependencies import (
    TokenClaims, require_system_admin, require_admin, validate_token_or_api_key
)
from ..services.credential_service import credential_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _provider_to_response(provider: LLMProvider) -> LLMProviderResponse:
    return LLMProviderResponse(
        id=provider.id,
        provider=provider.provider,
        model_id=provider.model_id,
        display_name=provider.display_name,
        base_url=provider.base_url,
        requires_api_key=provider.requires_api_key,
        has_system_api_key=provider.api_key_encrypted is not None,
        is_active=provider.is_active,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _selection_to_response(sel: TenantLLMSelection) -> TenantLLMSelectionResponse:
    p = sel.llm_provider
    return TenantLLMSelectionResponse(
        id=sel.id,
        tenant_id=sel.tenant_id,
        llm_provider_id=sel.llm_provider_id,
        provider=p.provider,
        model_id=p.model_id,
        display_name=p.display_name,
        base_url=p.base_url,
        has_tenant_api_key=sel.api_key_encrypted is not None,
        temperature=sel.temperature,
        is_active=sel.is_active,
        created_at=sel.created_at,
        updated_at=sel.updated_at,
    )


# ===================================================================
# Super-admin: LLM Provider Catalog
# ===================================================================

@router.post("/llm-providers", response_model=LLMProviderResponse, status_code=201)
async def create_llm_provider(
    request: LLMProviderCreateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Add an LLM provider to the system catalog (super-admin only)."""
    existing = db.query(LLMProvider).filter(
        LLMProvider.provider == request.provider,
        LLMProvider.model_id == request.model_id,
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider '{request.provider}' with model '{request.model_id}' already exists",
        )

    encrypted_key = None
    if request.api_key:
        encrypted_key = credential_service.encrypt({"api_key": request.api_key})

    provider = LLMProvider(
        provider=request.provider,
        model_id=request.model_id,
        display_name=request.display_name,
        base_url=request.base_url,
        api_key_encrypted=encrypted_key,
        requires_api_key=request.requires_api_key,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)

    logger.info(f"Created LLM provider: {request.provider}/{request.model_id}")
    return _provider_to_response(provider)


@router.get("/llm-providers", response_model=List[LLMProviderResponse])
async def list_llm_providers(
    active_only: bool = True,
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db),
):
    """List available LLM providers. All authenticated users can view."""
    query = db.query(LLMProvider)
    if active_only:
        query = query.filter(LLMProvider.is_active == True)
    providers = query.order_by(LLMProvider.display_name).all()
    return [_provider_to_response(p) for p in providers]


@router.get("/llm-providers/{provider_id}", response_model=LLMProviderResponse)
async def get_llm_provider(
    provider_id: str,
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db),
):
    """Get a specific LLM provider."""
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found")
    return _provider_to_response(provider)


@router.put("/llm-providers/{provider_id}", response_model=LLMProviderResponse)
async def update_llm_provider(
    provider_id: str,
    request: LLMProviderUpdateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Update an LLM provider in the catalog (super-admin only)."""
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found")

    if request.display_name is not None:
        provider.display_name = request.display_name
    if request.base_url is not None:
        provider.base_url = request.base_url
    if request.api_key is not None:
        provider.api_key_encrypted = credential_service.encrypt({"api_key": request.api_key})
    if request.requires_api_key is not None:
        provider.requires_api_key = request.requires_api_key
    if request.is_active is not None:
        provider.is_active = request.is_active

    db.commit()
    db.refresh(provider)
    return _provider_to_response(provider)


@router.delete("/llm-providers/{provider_id}", status_code=204)
async def delete_llm_provider(
    provider_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Delete an LLM provider from the catalog (super-admin only).

    Will fail if any tenants are currently using this provider.
    """
    provider = db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found")

    active_selections = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.llm_provider_id == provider_id,
    ).count()

    if active_selections > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete: {active_selections} tenant(s) are using this provider. "
                   "Deactivate it instead or reassign those tenants first.",
        )

    db.delete(provider)
    db.commit()


# ===================================================================
# Tenant admin: LLM Selection
# ===================================================================

@router.post("/llm-selection", response_model=TenantLLMSelectionResponse, status_code=201)
async def select_llm(
    request: TenantLLMSelectRequest,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Select an LLM provider for the tenant (tenant-admin only).

    Replaces any existing selection for this tenant.
    """
    # Verify the provider exists and is active
    provider = db.query(LLMProvider).filter(
        LLMProvider.id == request.llm_provider_id,
        LLMProvider.is_active == True,
    ).first()
    if not provider:
        raise HTTPException(status_code=404, detail="LLM provider not found or not active")

    # Validate: if provider requires API key, ensure one is available
    if provider.requires_api_key and not request.api_key and not provider.api_key_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This provider requires an API key. Provide one or ask your system admin to set a system-level key.",
        )

    # Remove existing selection for this tenant
    existing = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.tenant_id == claims.tenant_id,
    ).first()
    if existing:
        db.delete(existing)
        db.flush()

    encrypted_key = None
    if request.api_key:
        encrypted_key = credential_service.encrypt({"api_key": request.api_key})

    selection = TenantLLMSelection(
        tenant_id=claims.tenant_id,
        llm_provider_id=request.llm_provider_id,
        api_key_encrypted=encrypted_key,
        temperature=request.temperature,
    )
    db.add(selection)
    db.commit()
    db.refresh(selection)

    logger.info(
        f"Tenant {claims.tenant_id} selected LLM: {provider.provider}/{provider.model_id}"
    )
    return _selection_to_response(selection)


@router.get("/llm-selection", response_model=TenantLLMSelectionResponse)
async def get_llm_selection(
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db),
):
    """Get the current LLM selection for the tenant."""
    selection = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.tenant_id == claims.tenant_id,
    ).first()

    if not selection:
        raise HTTPException(
            status_code=404,
            detail="No LLM selected for this tenant. Use POST /llm-selection to choose one.",
        )

    return _selection_to_response(selection)


@router.put("/llm-selection", response_model=TenantLLMSelectionResponse)
async def update_llm_selection(
    request: TenantLLMUpdateRequest,
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update the tenant's LLM selection (tenant-admin only)."""
    selection = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.tenant_id == claims.tenant_id,
    ).first()

    if not selection:
        raise HTTPException(
            status_code=404,
            detail="No LLM selected for this tenant. Use POST /llm-selection first.",
        )

    if request.llm_provider_id is not None:
        provider = db.query(LLMProvider).filter(
            LLMProvider.id == request.llm_provider_id,
            LLMProvider.is_active == True,
        ).first()
        if not provider:
            raise HTTPException(status_code=404, detail="LLM provider not found or not active")
        selection.llm_provider_id = request.llm_provider_id

    if request.api_key is not None:
        selection.api_key_encrypted = credential_service.encrypt({"api_key": request.api_key})

    if request.temperature is not None:
        selection.temperature = request.temperature

    db.commit()
    db.refresh(selection)
    return _selection_to_response(selection)


@router.delete("/llm-selection", status_code=204)
async def delete_llm_selection(
    claims: TokenClaims = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove the tenant's LLM selection (reverts to system default)."""
    selection = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.tenant_id == claims.tenant_id,
    ).first()

    if not selection:
        raise HTTPException(status_code=404, detail="No LLM selection to delete")

    db.delete(selection)
    db.commit()