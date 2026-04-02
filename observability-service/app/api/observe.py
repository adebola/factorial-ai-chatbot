"""
Main observation query endpoint - invokes the LangChain agent.
"""
import uuid
import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.backend_config import ObservabilityBackend
from ..models.llm_provider import LLMProvider, TenantLLMSelection
from ..models.observation_session import ObservationSession
from ..models.observation_query import ObservationQuery
from ..schemas.observe import ObserveRequest, ObserveResponse, ObserveErrorResponse
from ..services.dependencies import TokenClaims, validate_token_or_api_key
from ..services.credential_service import credential_service
from ..services.response_formatter import format_full_response
from ..services.agent_service import (
    execute_agent_query, LLMConfig, BackendConfig
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_llm_config(tenant_id: str, db: Session) -> LLMConfig:
    """Load LLM config for a tenant.

    Priority:
    1. tenant_llm_selections → llm_providers (new tables)
    2. observability_backends with backend_type='llm' (legacy)
    3. Default OpenAI config
    """
    # 1. Check new tenant LLM selection
    selection = db.query(TenantLLMSelection).filter(
        TenantLLMSelection.tenant_id == tenant_id,
        TenantLLMSelection.is_active == True,
    ).first()

    if selection and selection.llm_provider:
        provider = selection.llm_provider
        if provider.is_active:
            # Resolve API key: tenant override → system-level → None
            api_key = None
            if selection.api_key_encrypted:
                creds = credential_service.decrypt(selection.api_key_encrypted)
                api_key = creds.get("api_key") if creds else None
            elif provider.api_key_encrypted:
                creds = credential_service.decrypt(provider.api_key_encrypted)
                api_key = creds.get("api_key") if creds else None

            return LLMConfig(
                provider=provider.provider,
                model=provider.model_id,
                api_key=api_key,
                base_url=provider.base_url,
                temperature=selection.temperature,
            )

    # 2. Legacy: observability_backends with backend_type='llm'
    legacy = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == "llm",
        ObservabilityBackend.is_active == True,
    ).first()

    if legacy and legacy.credentials_encrypted:
        creds = credential_service.decrypt(legacy.credentials_encrypted)
        if creds:
            return LLMConfig(
                provider=creds.get("provider", "openai"),
                model=creds.get("model", "gpt-4o"),
                api_key=creds.get("api_key"),
                base_url=creds.get("base_url") or legacy.url,
                temperature=creds.get("temperature", 0),
            )

    # 3. Default
    return LLMConfig()


def _load_backend_configs(
    tenant_id: str, db: Session
) -> tuple[Dict[str, BackendConfig], LLMConfig]:
    """Load backend configs and LLM config for a tenant from the database."""
    backends = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.is_active == True
    ).all()

    if not backends:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No observability backends configured for this tenant"
        )

    backend_configs = {}
    for backend in backends:
        if backend.backend_type == "llm":
            continue  # LLM config loaded separately

        creds = None
        if backend.credentials_encrypted:
            creds = credential_service.decrypt(backend.credentials_encrypted)

        backend_configs[backend.backend_type] = BackendConfig(
            url=backend.url,
            auth_type=backend.auth_type,
            credentials=creds,
            verify_ssl=backend.verify_ssl,
            timeout_seconds=backend.timeout_seconds,
        )

    llm_config = _load_llm_config(tenant_id, db)
    return backend_configs, llm_config


@router.post("/query", response_model=ObserveResponse)
async def query_observability(
    request: ObserveRequest,
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db)
):
    """Execute an observability query through the AI agent.

    The agent dynamically selects which observability backends to query
    (Prometheus, Jaeger, Elasticsearch, K8s API, etc.) and synthesizes
    a coherent answer with root cause analysis.
    """
    tenant_id = request.tenant_id or claims.tenant_id

    # Verify tenant access
    if not claims.is_system_admin and tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot query observability for other tenants"
        )

    # Get or create observability session
    # Note: the caller (e.g. chat service) may pass its own session_id which won't
    # exist in the observability DB. In that case, create a new observability session
    # and link it via chat_session_id for correlation.
    session_id = request.session_id
    if session_id:
        session = db.query(ObservationSession).filter(
            ObservationSession.id == session_id,
            ObservationSession.tenant_id == tenant_id
        ).first()
        if not session:
            # Session ID is from another service (e.g. chat) — create a new
            # observability session linked to it
            session = ObservationSession(
                tenant_id=tenant_id,
                chat_session_id=session_id
            )
            db.add(session)
            db.flush()
            session_id = session.id
    else:
        session = ObservationSession(
            tenant_id=tenant_id
        )
        db.add(session)
        db.flush()
        session_id = session.id

    # Load backend configs
    backend_configs, llm_config = _load_backend_configs(tenant_id, db)

    # Execute agent
    query_id = str(uuid.uuid4())
    result = await execute_agent_query(
        backend_configs=backend_configs,
        llm_config=llm_config,
        message=request.message,
        conversation_history=request.conversation_history
    )

    logger.info(
        f"Agent finished for tenant {tenant_id}: status={result.status}, "
        f"response_length={len(result.response)}, tool_calls={len(result.tool_calls)}, "
        f"duration={result.total_duration_ms:.0f}ms"
    )

    # Save query record
    query_record = ObservationQuery(
        id=query_id,
        session_id=session_id,
        tenant_id=tenant_id,
        user_message=request.message,
        agent_response=result.response,
        tool_calls=result.tool_calls,
        total_duration_ms=result.total_duration_ms,
        llm_tokens_used=result.llm_tokens_used,
        status=result.status,
        error_message=result.error_message
    )
    db.add(query_record)
    db.commit()
    logger.info(f"Query record saved: {query_id}")

    if result.status == "error":
        logger.error(
            f"Agent query failed for tenant {tenant_id}: {result.error_message}",
            extra={"tenant_id": tenant_id, "query_id": query_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error_message or "Agent query failed"
        )

    logger.info(f"Returning response for query {query_id}")

    # Format tool calls for response
    formatted_tool_calls = [
        {
            "tool": tc["tool"],
            "input": tc["input"],
            "output": tc["output"],
            "duration_ms": tc.get("duration_ms", 0)
        }
        for tc in result.tool_calls
    ]

    # Generate structured content blocks from the response and tool results
    blocks = format_full_response(result.response, result.tool_calls)

    # Suggest actions based on what was found
    suggested_actions = []
    if result.tool_calls:
        suggested_actions.append("Export as PDF")
    if any(tc["tool"] in ("prometheus_query", "otel_metrics") for tc in result.tool_calls):
        suggested_actions.append("View metrics dashboard")
    if any(tc["tool"] in ("prometheus_alerts",) for tc in result.tool_calls):
        suggested_actions.append("View all alerts")
    if any(tc["tool"] in ("search_logs", "elasticsearch_search") for tc in result.tool_calls):
        suggested_actions.append("Search more logs")

    return ObserveResponse(
        response=result.response,
        response_type="rich",
        blocks=blocks,
        tool_calls=formatted_tool_calls,
        suggested_actions=suggested_actions,
        session_id=session_id,
        query_id=query_id,
        total_duration_ms=result.total_duration_ms,
        llm_tokens_used=result.llm_tokens_used
    )
