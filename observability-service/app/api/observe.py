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
from ..models.observation_session import ObservationSession
from ..models.observation_query import ObservationQuery
from ..schemas.observe import ObserveRequest, ObserveResponse, ObserveErrorResponse
from ..services.dependencies import TokenClaims, validate_token_or_api_key
from ..services.credential_service import credential_service
from ..services.agent_service import (
    execute_agent_query, LLMConfig, BackendConfig
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
    llm_config = LLMConfig()  # Default to OpenAI

    for backend in backends:
        # Decrypt credentials
        creds = None
        if backend.credentials_encrypted:
            creds = credential_service.decrypt(backend.credentials_encrypted)

        if backend.backend_type == "llm":
            # LLM provider config
            if creds:
                llm_config = LLMConfig(
                    provider=creds.get("provider", "openai"),
                    model=creds.get("model", "gpt-4o"),
                    api_key=creds.get("api_key"),
                    base_url=creds.get("base_url") or backend.url,
                    temperature=creds.get("temperature", 0)
                )
        else:
            backend_configs[backend.backend_type] = BackendConfig(
                url=backend.url,
                auth_type=backend.auth_type,
                credentials=creds,
                verify_ssl=backend.verify_ssl,
                timeout_seconds=backend.timeout_seconds
            )

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

    # Get or create session
    session_id = request.session_id
    if session_id:
        session = db.query(ObservationSession).filter(
            ObservationSession.id == session_id,
            ObservationSession.tenant_id == tenant_id
        ).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
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

    if result.status == "error":
        logger.error(
            f"Agent query failed for tenant {tenant_id}: {result.error_message}",
            extra={"tenant_id": tenant_id, "query_id": query_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error_message or "Agent query failed"
        )

    return ObserveResponse(
        response=result.response,
        tool_calls=[
            {
                "tool": tc["tool"],
                "input": tc["input"],
                "output": tc["output"],
                "duration_ms": tc.get("duration_ms", 0)
            }
            for tc in result.tool_calls
        ],
        session_id=session_id,
        query_id=query_id,
        total_duration_ms=result.total_duration_ms,
        llm_tokens_used=result.llm_tokens_used
    )
