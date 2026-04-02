"""
Admin CRUD endpoints for the platform-wide LLM Provider Config registry.

Super-admin manages available models and their context window limits.
Also exposes internal endpoints for service-to-service lookups.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.llm_provider import LLMProviderConfig
from ..schemas.llm_provider import (
    LLMProviderConfigCreate,
    LLMProviderConfigUpdate,
    LLMProviderConfigResponse,
)
from ..services.dependencies import TokenClaims, require_system_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Admin CRUD (SYSTEM_ADMIN only) ──

@router.post("/", response_model=LLMProviderConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_provider(
    request: LLMProviderConfigCreate,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Register a new LLM model configuration."""
    existing = db.query(LLMProviderConfig).filter(
        LLMProviderConfig.provider == request.provider,
        LLMProviderConfig.model_name == request.model_name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{request.provider}/{request.model_name}' already registered",
        )

    if request.context_limit_tokens > request.max_context_tokens:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="context_limit_tokens cannot exceed max_context_tokens",
        )

    config = LLMProviderConfig(
        provider=request.provider,
        model_name=request.model_name,
        display_name=request.display_name,
        max_context_tokens=request.max_context_tokens,
        context_limit_tokens=request.context_limit_tokens,
        max_response_tokens=request.max_response_tokens,
        cost_per_input_token=request.cost_per_input_token,
        cost_per_output_token=request.cost_per_output_token,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    logger.info(f"LLM provider config created: {config.provider}/{config.model_name} by {claims.email}")
    return LLMProviderConfigResponse.from_orm(config)


@router.get("/", response_model=List[LLMProviderConfigResponse])
async def list_llm_providers(
    include_inactive: bool = False,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """List all LLM provider configurations."""
    query = db.query(LLMProviderConfig)
    if not include_inactive:
        query = query.filter(LLMProviderConfig.is_active == True)
    configs = query.order_by(LLMProviderConfig.provider, LLMProviderConfig.model_name).all()
    return [LLMProviderConfigResponse.from_orm(c) for c in configs]


@router.get("/{config_id}", response_model=LLMProviderConfigResponse)
async def get_llm_provider(
    config_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Get a specific LLM provider configuration."""
    config = db.query(LLMProviderConfig).filter(LLMProviderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM provider config not found")
    return LLMProviderConfigResponse.from_orm(config)


@router.put("/{config_id}", response_model=LLMProviderConfigResponse)
async def update_llm_provider(
    config_id: str,
    request: LLMProviderConfigUpdate,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Update an LLM provider configuration (especially context limits)."""
    config = db.query(LLMProviderConfig).filter(LLMProviderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM provider config not found")

    update_data = request.dict(exclude_unset=True)

    # Validate context_limit_tokens vs max_context_tokens
    new_limit = update_data.get("context_limit_tokens", config.context_limit_tokens)
    new_max = update_data.get("max_context_tokens", config.max_context_tokens)
    if new_limit > new_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="context_limit_tokens cannot exceed max_context_tokens",
        )

    for field, value in update_data.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)
    logger.info(f"LLM provider config updated: {config.provider}/{config.model_name} by {claims.email}")
    return LLMProviderConfigResponse.from_orm(config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(
    config_id: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    """Deactivate an LLM provider configuration."""
    config = db.query(LLMProviderConfig).filter(LLMProviderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM provider config not found")
    config.is_active = False
    db.commit()
    logger.info(f"LLM provider config deactivated: {config.provider}/{config.model_name} by {claims.email}")


# ── Internal Service-to-Service Endpoints (no auth) ──

@router.get("/lookup/{provider}/{model_name}", response_model=LLMProviderConfigResponse)
async def lookup_llm_provider(
    provider: str,
    model_name: str,
    db: Session = Depends(get_db),
):
    """
    Look up an LLM provider config by provider + model_name.

    Internal endpoint used by the agent gateway to fetch context limits
    for a specific model. No authentication required.
    """
    config = db.query(LLMProviderConfig).filter(
        LLMProviderConfig.provider == provider,
        LLMProviderConfig.model_name == model_name,
        LLMProviderConfig.is_active == True,
    ).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active config for {provider}/{model_name}",
        )
    return LLMProviderConfigResponse.from_orm(config)
