"""Agent Chat WebSocket handler and REST API endpoints.

Provides a dedicated communication channel for agentic services,
completely separate from the RAG chat pipeline. Requires OAuth2
authentication (not API key).
"""
import asyncio
import io
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from fastapi import (
    APIRouter, Body, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, Query, status
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging_config import get_logger
from ..models.agent_models import AgentSession, AgentMessage
from ..services.agent_session_service import agent_session_service
from ..services.context_builder import count_tokens, build_context
from ..services.dependencies import TokenClaims, validate_token
from ..services.audit_publisher import audit_publisher
from ..services.jwt_validator import jwt_validator

logger = get_logger("agent_ws")


# ═══════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════

class AgentConnectionManager:
    """Manages active agent WebSocket connections."""

    def __init__(self):
        self.session_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.session_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        self.session_connections.pop(session_id, None)


agent_manager = AgentConnectionManager()


# ═══════════════════════════════════════════════════════════
# WEBSOCKET HANDLER
# ═══════════════════════════════════════════════════════════

class AgentChatHandler:
    """Handles a single agent WebSocket connection."""

    def __init__(self, db: Session):
        self.db = db
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=10),
                timeout=aiohttp.ClientTimeout(total=120),
            )
        return self._http_session

    async def handle_connection(
        self,
        websocket: WebSocket,
        service_key: str,
        token: Optional[str],
        session_id: Optional[str],
    ):
        """Main WebSocket connection handler for agent chat."""

        # 1. Authenticate (required for agent chat)
        claims = await self._authenticate(token)
        if not claims:
            await websocket.close(code=4001, reason="Authentication required")
            return

        tenant_id = claims.tenant_id
        user_id = claims.user_id

        # 2. Verify service access
        service_info = await self._get_service_info(tenant_id, service_key)
        if not service_info:
            await websocket.close(code=4003, reason=f"No access to service '{service_key}'")
            return

        # 3. Get or create session
        context_limit = await self._get_context_limit(service_info)
        session, is_new = agent_session_service.get_or_create_session(
            db=self.db,
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=claims.email,
            user_full_name=claims.full_name,
            service_key=service_key,
            session_id=session_id,
            model_name=service_info.get("config", {}).get("model_name"),
            context_limit_tokens=context_limit,
        )

        # Audit: new session created
        if is_new:
            try:
                await audit_publisher.publish(
                    action_type="agent.session.created",
                    tier="data",
                    source_service="chat-service",
                    tenant_id=tenant_id,
                    actor_user_id=user_id,
                    actor_email=claims.email,
                    resource_type="agent_session",
                    resource_id=session.id,
                    after_state={"service_key": service_key},
                )
            except Exception:
                pass  # Never break business logic

        # 4. Connect
        await agent_manager.connect(websocket, session.id)

        try:
            # 5. Send welcome message
            welcome = {
                "type": "welcome",
                "session": self._session_to_dict(session),
                "service": {
                    "service_key": service_info["service_key"],
                    "service_name": service_info.get("service_name"),
                    "description": service_info.get("description"),
                    "ui_hints": service_info.get("ui_hints"),
                },
            }

            # Include history if resuming
            if not is_new:
                history = await agent_session_service.get_conversation_history(self.db, session.id)
                welcome["history"] = history

            await websocket.send_text(json.dumps(welcome, default=str))

            # 6. Message loop
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)

                if data.get("type") == "message":
                    await self._handle_message(
                        websocket=websocket,
                        session=session,
                        service_info=service_info,
                        user_message=data.get("content", ""),
                        access_token=token,
                    )
                elif data.get("type") == "new_session":
                    # Client requests a fresh session
                    session, _ = agent_session_service.get_or_create_session(
                        db=self.db,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        user_email=claims.email,
                        user_full_name=claims.full_name,
                        service_key=service_key,
                        model_name=service_info.get("config", {}).get("model_name"),
                        context_limit_tokens=context_limit,
                    )
                    await websocket.send_text(json.dumps({
                        "type": "session_created",
                        "session": self._session_to_dict(session),
                    }, default=str))
                elif data.get("type") == "switch_session":
                    target_id = data.get("session_id")
                    target = agent_session_service.get_session(self.db, target_id)
                    if target and target.tenant_id == tenant_id and target.user_id == user_id:
                        agent_manager.disconnect(session.id)
                        session = target
                        agent_manager.session_connections[session.id] = websocket
                        history = await agent_session_service.get_conversation_history(self.db, session.id)
                        await websocket.send_text(json.dumps({
                            "type": "session_switched",
                            "session": self._session_to_dict(session),
                            "history": history,
                        }, default=str))

        except WebSocketDisconnect:
            logger.info("Agent WebSocket disconnected", session_id=session.id)
        except Exception as e:
            logger.error("Agent WebSocket error", error=str(e), session_id=session.id)
        finally:
            agent_manager.disconnect(session.id)
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()

    async def _handle_message(
        self,
        websocket: WebSocket,
        session: AgentSession,
        service_info: dict,
        user_message: str,
        access_token: Optional[str],
    ):
        """Process a user message: save, forward to agent service, save response."""
        t_start = time.time()

        if not user_message.strip():
            return

        # Count tokens accurately using tiktoken
        model_name = session.model_name or "gpt-4o"
        user_token_count = count_tokens(user_message, model_name)

        # Check context overflow before processing
        if agent_session_service.check_overflow(session, user_token_count):
            carry_over = service_info.get("config", {}).get("context_carry_over_enabled", False)
            context_summary = None
            if carry_over:
                context_summary = await self._summarize_session(session)

            new_session = agent_session_service.handle_overflow(
                db=self.db, session=session, context_summary=context_summary
            )
            await websocket.send_text(json.dumps({
                "type": "session_overflow",
                "old_session_id": session.id,
                "new_session_id": new_session.id,
                "has_context_summary": context_summary is not None,
                "message": "Context limit reached. Continuing in new session.",
            }))

            # Audit: session overflow
            try:
                await audit_publisher.publish(
                    action_type="agent.session.overflow",
                    tier="data",
                    source_service="chat-service",
                    tenant_id=session.tenant_id,
                    actor_user_id=session.user_id,
                    resource_type="agent_session",
                    resource_id=new_session.id,
                    before_state={"old_session_id": session.id},
                    after_state={"has_context_summary": context_summary is not None},
                )
            except Exception:
                pass  # Never break business logic

            # Update local reference
            agent_manager.disconnect(session.id)
            session = new_session
            agent_manager.session_connections[session.id] = websocket

            # Re-refresh for the DB to track the new session
            self.db.refresh(session)

        # Save user message with accurate token count
        user_msg = await agent_session_service.save_message(
            db=self.db,
            session=session,
            role="user",
            content=user_message,
            token_count=user_token_count,
        )

        # Send typing indicator
        await websocket.send_text(json.dumps({"type": "typing", "is_typing": True}))

        # Build token-aware conversation history for the agent
        history = await agent_session_service.get_conversation_history(self.db, session.id)
        # Exclude the user message we just saved (last in list) — it's the current message
        prior_history = [
            h for h in history[:-1]
            if h.get("role") in ("user", "assistant")
        ]

        if session.context_limit_tokens:
            # Use context builder for token-aware history assembly
            max_response = config.get("max_response_tokens", 4096)
            system_prompt = ""  # Agent services define their own system prompt
            _, _, _ = build_context(
                system_prompt=system_prompt,
                current_message=user_message,
                history=prior_history,
                context_limit_tokens=session.context_limit_tokens,
                max_response_tokens=max_response,
                context_summary=session.context_summary,
                model_name=model_name,
            )
            # The context builder returns the trimmed messages, but the agent
            # service manages its own system prompt. So we extract just the
            # history portion that fits within budget.
            conversation_history = [
                {"role": h["role"], "content": h["content"]}
                for h in prior_history
            ]
            # Re-trim using budget (build_context already did this, but we
            # need to replicate the trimming for the flat list we send)
            budget = session.context_limit_tokens - user_token_count - config.get("max_response_tokens", 4096)
            trimmed = []
            for msg in reversed(prior_history):
                tc = msg.get("token_count", 0) or count_tokens(msg.get("content", ""), model_name)
                if tc > budget:
                    break
                trimmed.insert(0, msg)
                budget -= tc
            conversation_history = [{"role": m["role"], "content": m["content"]} for m in trimmed]
        else:
            # No context limit — send full history
            conversation_history = [
                {"role": h["role"], "content": h["content"]}
                for h in prior_history
            ]

        # Include context summary from parent session if present
        if session.context_summary and conversation_history:
            conversation_history.insert(0, {
                "role": "system",
                "content": f"Context from previous session:\n{session.context_summary}"
            })

        # Forward to agentic service
        config = service_info.get("config", {})
        base_url = service_info.get("base_url", "").rstrip("/")
        query_endpoint = config.get("query_endpoint", "/api/v1/query")
        timeout = config.get("timeout_seconds", 120)

        try:
            http = await self._get_http_session()
            payload = {
                "tenant_id": session.tenant_id,
                "session_id": session.id,
                "message": user_message,
                "conversation_history": conversation_history,
            }
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

            async with http.post(
                f"{base_url}{query_endpoint}",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                else:
                    body = await resp.text()
                    logger.error(
                        "Agentic service returned error",
                        status=resp.status,
                        body=body[:500],
                        service_key=service_info["service_key"],
                    )
                    result = {"response": f"Agent service error (HTTP {resp.status}). Please try again."}

        except asyncio.TimeoutError:
            logger.error("Agentic service timeout", service_key=service_info["service_key"])
            result = {"response": "The agent took too long to respond. Please try again."}
        except Exception as e:
            logger.error("Agentic service request failed", error=str(e))
            result = {"response": "Failed to reach the agent service. Please try again."}

        # Stop typing indicator
        await websocket.send_text(json.dumps({"type": "typing", "is_typing": False}))

        # Extract response content
        response_text = result.get("response", "")
        structured_blocks = result.get("blocks")
        tool_calls = result.get("tool_calls")
        token_usage = result.get("token_usage", result.get("llm_tokens_used"))

        # Count response tokens — prefer the agent's reported usage, fall back to counting
        if isinstance(token_usage, dict) and token_usage.get("completion_tokens"):
            response_token_count = token_usage["completion_tokens"]
        else:
            response_token_count = count_tokens(response_text, model_name)

        # Save assistant message
        ai_msg = await agent_session_service.save_message(
            db=self.db,
            session=session,
            role="assistant",
            content=response_text,
            token_count=response_token_count,
            structured_blocks=structured_blocks,
            tool_calls=tool_calls,
            metadata={
                "service_key": service_info["service_key"],
                "query_id": result.get("query_id"),
                "total_duration_ms": result.get("total_duration_ms"),
                "token_usage": token_usage,
            },
        )

        t_end = time.time()

        # Send response to client
        response_msg = {
            "type": "response",
            "message": {
                "id": ai_msg.id,
                "role": "assistant",
                "content": response_text,
                "structured_blocks": structured_blocks,
                "tool_calls": tool_calls,
                "token_count": response_token_count,
                "created_at": ai_msg.created_at.isoformat() if ai_msg.created_at else None,
            },
            "session_update": {
                "total_tokens_used": session.total_tokens_used,
                "context_limit_tokens": session.context_limit_tokens,
            },
            "metadata": {
                "service_key": service_info["service_key"],
                "query_id": result.get("query_id"),
                "total_duration_ms": round((t_end - t_start) * 1000),
                "suggested_actions": result.get("suggested_actions", []),
            },
        }
        await websocket.send_text(json.dumps(response_msg, default=str))

    # ── Helpers ──

    async def _authenticate(self, token: Optional[str]) -> Optional[TokenClaims]:
        """Validate OAuth2 token for WebSocket connection."""
        if not token:
            return None
        try:
            token_info = await jwt_validator.validate_token(token)
            if not token_info:
                return None
            tenant_id = token_info.get("tenant_id")
            user_id = token_info.get("user_id") or token_info.get("sub")
            if not tenant_id or not user_id:
                return None
            return TokenClaims(
                tenant_id=tenant_id,
                user_id=user_id,
                email=token_info.get("email"),
                full_name=token_info.get("full_name"),
                authorities=token_info.get("authorities", []),
                access_token=token,
            )
        except Exception as e:
            logger.warning("Agent WebSocket auth failed", error=str(e))
            return None

    async def _get_service_info(self, tenant_id: str, service_key: str) -> Optional[dict]:
        """Check service access and get service details from billing service."""
        billing_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
        try:
            http = await self._get_http_session()
            async with http.get(
                f"{billing_url}/api/v1/restrictions/check/active-agentics/{tenant_id}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("has_services"):
                    return None
                # Find the specific service
                for svc in data.get("services", []):
                    if svc["service_key"] == service_key:
                        return svc
                return None
        except Exception as e:
            logger.error("Failed to check service access", error=str(e))
            return None

    async def _get_context_limit(self, service_info: dict) -> Optional[int]:
        """Get context limit from service config or model registry."""
        config = service_info.get("config", {})
        # Direct config override takes priority
        if config.get("context_limit_tokens"):
            return config["context_limit_tokens"]

        # Query the model registry for the configured model's limit
        model_name = config.get("model_name")
        if model_name:
            billing_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
            try:
                # Infer provider from model name
                provider = "openai"
                if "claude" in model_name.lower():
                    provider = "anthropic"
                elif "llama" in model_name.lower() or "mistral" in model_name.lower():
                    provider = "ollama"

                http = await self._get_http_session()
                async with http.get(
                    f"{billing_url}/api/v1/admin/model-registry/lookup/{provider}/{model_name}",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("context_limit_tokens")
            except Exception as e:
                logger.warning("Failed to fetch model context limit", error=str(e), model=model_name)

        return None

    async def _summarize_session(self, session: AgentSession) -> Optional[str]:
        """Generate a summary of the session for context carry-over."""
        try:
            history = await agent_session_service.get_conversation_history(self.db, session.id)
            if not history:
                return None

            # Build a concise conversation for summarization
            conv_text = "\n".join(
                f"{h['role']}: {h['content'][:500]}" for h in history[-20:]  # Last 20 messages
            )

            # Use OpenAI to summarize (cheap model)
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Summarize this conversation concisely in 2-3 paragraphs. Focus on key topics discussed, decisions made, and outstanding questions."},
                    {"role": "user", "content": conv_text},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("Failed to summarize session for carry-over", error=str(e))
            return None

    def _session_to_dict(self, session: AgentSession) -> dict:
        return {
            "id": session.id,
            "service_key": session.service_key,
            "parent_session_id": session.parent_session_id,
            "status": session.status,
            "total_tokens_used": session.total_tokens_used or 0,
            "context_limit_tokens": session.context_limit_tokens,
            "model_name": session.model_name,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        }


# ═══════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINT
# ═══════════════════════════════════════════════════════════

async def agent_websocket_endpoint(
    websocket: WebSocket,
    service_key: str,
    token: str = Query(None, description="OAuth2 access token"),
    session_id: str = Query(None, description="Resume an existing session"),
    db: Session = Depends(get_db),
):
    """WebSocket endpoint for agent chat. Requires OAuth2 authentication."""
    handler = AgentChatHandler(db)
    await handler.handle_connection(websocket, service_key, token, session_id)


# ═══════════════════════════════════════════════════════════
# REST API ENDPOINTS
# ═══════════════════════════════════════════════════════════

agent_chat_router = APIRouter(tags=["agent-chat"])


@agent_chat_router.get("/catalog")
async def get_agent_catalog(
    claims: TokenClaims = Depends(validate_token),
):
    """Get the agent catalog for the authenticated user's tenant."""
    billing_url = os.environ.get("BILLING_SERVICE_URL", "http://localhost:8004")
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{billing_url}/api/v1/restrictions/check/active-agentics/{claims.tenant_id}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"has_services": False, "services": []}
    except Exception as e:
        logger.error("Failed to fetch agent catalog", error=str(e))
        return {"has_services": False, "services": []}


@agent_chat_router.get("/sessions")
async def list_agent_sessions(
    service_key: str = Query(..., description="Filter by service key"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """List agent sessions for the authenticated user."""
    sessions = agent_session_service.list_sessions(
        db=db,
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        service_key=service_key,
    )
    return [
        {
            "id": s.id,
            "service_key": s.service_key,
            "parent_session_id": s.parent_session_id,
            "status": s.status,
            "total_tokens_used": s.total_tokens_used or 0,
            "context_limit_tokens": s.context_limit_tokens,
            "model_name": s.model_name,
            "message_count": len(s.messages) if s.messages else 0,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_activity": s.last_activity.isoformat() if s.last_activity else None,
        }
        for s in sessions
    ]


@agent_chat_router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Get messages for a session."""
    session = agent_session_service.get_session(db, session_id)
    if not session or session.tenant_id != claims.tenant_id or session.user_id != claims.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
        .all()
    )
    return [
        {
            "id": m.id,
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "structured_blocks": m.structured_blocks,
            "token_count": m.token_count,
            "tool_calls": m.tool_calls,
            "message_metadata": m.message_metadata,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@agent_chat_router.post("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query(..., pattern="^(pdf|pptx|docx)$", description="Export format"),
    message_ids: Optional[List[str]] = Body(None, description="Specific message IDs to export"),
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    """Export an agent session as PDF, PPTX, or DOCX."""
    session = agent_session_service.get_session(db, session_id)
    if not session or session.tenant_id != claims.tenant_id or session.user_id != claims.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    from ..services.document_generator import document_generator
    try:
        content = document_generator.export_session(
            db=db,
            session_id=session_id,
            format=format,
            message_ids=message_ids,
        )
    except Exception as e:
        logger.error("Document export failed", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )

    # Audit: export requested
    try:
        await audit_publisher.publish(
            action_type="agent.export.requested",
            tier="data",
            source_service="chat-service",
            tenant_id=claims.tenant_id,
            actor_user_id=claims.user_id,
            actor_email=claims.email,
            resource_type="agent_session",
            resource_id=session_id,
            after_state={"format": format},
        )
    except Exception:
        pass  # Never break business logic

    filename = f"session-{session_id[:8]}.{format}"
    return StreamingResponse(
        io.BytesIO(content),
        media_type=MIME_TYPES[format],
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
