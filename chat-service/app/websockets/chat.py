from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
import asyncio
import json
import uuid
import time
from datetime import datetime, timedelta

from ..core.database import get_db
from ..models.chat_models import ChatSession, ChatMessage
from ..services.chat_service import ChatService
from ..services.tenant_client import TenantClient
from ..services.workflow_client import WorkflowClient
from ..services.event_publisher import event_publisher
from ..services.usage_cache import usage_cache
from ..services.session_auth_service import session_auth_service
from ..core.logging_config import get_logger

logger = get_logger("ws")


class ConnectionManager:
    def __init__(self):
        # tenant_id -> List[WebSocket connections]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # session_id -> WebSocket
        self.session_connections: Dict[str, WebSocket] = {}
        # session_id -> tenant_id mapping
        self.session_tenants: Dict[str, str] = {}
    
    async def connect(self, websocket: WebSocket, tenant_id: str, session_id: str):
        await websocket.accept()
        
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = []
        
        self.active_connections[tenant_id].append(websocket)
        self.session_connections[session_id] = websocket
        self.session_tenants[session_id] = tenant_id
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.session_connections:
            tenant_id = self.session_tenants[session_id]
            
            # Remove from tenant connections
            if tenant_id in self.active_connections:
                if websocket in self.active_connections[tenant_id]:
                    self.active_connections[tenant_id].remove(websocket)
                
                # Clean up empty tenant connection list
                if not self.active_connections[tenant_id]:
                    del self.active_connections[tenant_id]
            
            # Clean up session mappings
            del self.session_connections[session_id]
            del self.session_tenants[session_id]
    
    async def send_personal_message(self, message: str, session_id: str):
        if session_id in self.session_connections:
            websocket = self.session_connections[session_id]
            await websocket.send_text(message)
    
    async def send_to_tenant(self, message: str, tenant_id: str):
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_text(message)


manager = ConnectionManager()


class ChatWebSocket:
    def __init__(self, db: Session):
        self.db = db
        self.tenant_client = TenantClient()
        self.chat_service = ChatService(db)
        self.workflow_client = None  # Will be initialized with API key after tenant is identified
    
    def _get_current_access_token(self, session_id: str) -> Optional[str]:
        """Read access token from Redis per-use (not cached) so refreshed tokens are picked up."""
        if not self._is_authenticated:
            return None
        return session_auth_service.get_access_token(session_id)

    def _get_user_claims(self, session_id: str) -> Optional[Dict]:
        """Extract user identity claims from session auth data for workflow variable injection."""
        if not self._is_authenticated:
            return None
        auth_data = session_auth_service.get_session_auth(session_id)
        if not auth_data or not auth_data.get("user_info"):
            return None
        info = auth_data["user_info"]
        return {"email": info.get("email"), "name": info.get("name"), "sub": info.get("sub")}

    async def handle_connection(self, websocket: WebSocket, api_key: str = None, tenant_id: str = None, user_identifier: str = None, session_id: str = None):
        # Identify tenant (no authentication required)
        tenant = None

        if api_key:
            # Try to find a tenant by API key
            tenant = await self.tenant_client.get_tenant_by_api_key(api_key)
        elif tenant_id:
            # Try to find a tenant by ID
            tenant = await self.tenant_client.get_tenant_by_id(tenant_id)

        if not tenant:
            await websocket.close(code=4000, reason="Tenant not found. Please provide valid api_key or tenant_id")
            return

        # Initialize workflow client with tenant's API key
        tenant_api_key = tenant.get("api_key") or api_key  # Use tenant's API key from the tenant object, or the one provided
        self.workflow_client = WorkflowClient(api_key=tenant_api_key)

        tenant_id = tenant["id"]  # tenant is now a dict from HTTP API

        # Session resumption: if session_id provided, try to resume an existing session
        is_authenticated = False
        auth_expired = False
        existing_session_resumed = False
        if session_id:
            existing_session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id,
                ChatSession.tenant_id == tenant_id,
                ChatSession.is_active == True
            ).first()

            # Fallback: find recently-inactive session (within 24h)
            # This handles page navigations on non-SPA sites where disconnect sets is_active=False
            if not existing_session:
                existing_session = self.db.query(ChatSession).filter(
                    ChatSession.session_id == session_id,
                    ChatSession.tenant_id == tenant_id,
                    ChatSession.is_active == False,
                    ChatSession.last_activity > datetime.now() - timedelta(hours=24)
                ).first()
                if existing_session:
                    existing_session.is_active = True
                    logger.info(f"Reactivated inactive session {session_id} for tenant {tenant_id}")

            if existing_session:
                existing_session_resumed = True
                # Resume the existing session
                if existing_session.is_authenticated:
                    # Verify tokens still exist in Redis (not just DB flag)
                    token = session_auth_service.get_access_token(session_id)
                    if token:
                        is_authenticated = True
                        user_identifier = user_identifier or existing_session.auth_user_email or existing_session.user_identifier
                    else:
                        is_authenticated = False
                        auth_expired = True
                        logger.info(f"Session {session_id} tokens expired in Redis, marking auth_expired")
                chat_session = existing_session
                logger.info(f"Resumed session {session_id}, authenticated={is_authenticated}, auth_expired={auth_expired}")
            else:
                # session_id not found — fall through to create new session
                session_id = str(uuid.uuid4())
                chat_session = ChatSession(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    user_identifier=user_identifier,
                    is_active=True
                )
                self.db.add(chat_session)
                await asyncio.get_event_loop().run_in_executor(None, self.db.commit)
        else:
            # Create a new anonymous session
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                tenant_id=tenant_id,
                session_id=session_id,
                user_identifier=user_identifier,
                is_active=True
            )
            self.db.add(chat_session)
            await asyncio.get_event_loop().run_in_executor(None, self.db.commit)

        # Store auth state for use during message processing
        self._is_authenticated = is_authenticated

        await manager.connect(websocket, tenant_id, session_id)

        # Prefetch usage limits to warm the cache
        try:
            await usage_cache.prefetch_for_tenant(tenant_id, tenant_api_key)
        except Exception as e:
            # Log but don't fail connection on cache warming error
            print(f"Failed to prefetch usage limits: {str(e)}")

        try:
            # Send a welcome message
            welcome_msg = {
                "type": "connection",
                "session_id": session_id,
                "message": "Connected to chat service",
                "authenticated": is_authenticated,
                "timestamp": datetime.now().isoformat()
            }
            if is_authenticated and chat_session.auth_user_name:
                welcome_msg["user"] = {
                    "name": chat_session.auth_user_name,
                    "email": chat_session.auth_user_email
                }
            await websocket.send_text(json.dumps(welcome_msg))

            # Notify widget if tokens expired since last connection
            if auth_expired:
                await websocket.send_text(json.dumps({
                    "type": "auth_expired",
                    "message": "Your session has expired. Please log in again."
                }))

            # Send chat history on session resumption so the widget can restore the UI
            if existing_session_resumed:
                try:
                    history_messages = self.db.query(ChatMessage).filter(
                        ChatMessage.session_id == session_id,
                        ChatMessage.tenant_id == tenant_id
                    ).order_by(ChatMessage.created_at.asc()).limit(50).all()

                    if history_messages:
                        history_data = [{
                            "role": msg.message_type,
                            "content": msg.content,
                            "message_id": msg.id,
                            "timestamp": msg.created_at.isoformat()
                        } for msg in history_messages]

                        await websocket.send_text(json.dumps({
                            "type": "history",
                            "messages": history_data,
                            "session_id": session_id
                        }))
                except Exception as e:
                    logger.error(f"Failed to send chat history: {str(e)}", extra={"session_id": session_id})

            while True:
                # Receive a message from client
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # Validate message format
                if "message" not in message_data:
                    error_msg = {
                        "type": "error",
                        "message": "Invalid message format"
                    }
                    await websocket.send_text(json.dumps(error_msg))
                    continue
                
                user_message = message_data["message"]
                t_start = time.time()

                # Check chat usage limits BEFORE processing message
                try:
                    # Fast path: check Redis cache (~1ms) instead of HTTP to billing service
                    allowed, reason = await usage_cache.check_chat_allowed(tenant_id, api_key=tenant_api_key)
                    if not allowed:
                        # Send limit exceeded error to client
                        limit_error_msg = {
                            "type": "error",
                            "message": f"Chat limit exceeded: {reason}",
                            "error_code": "LIMIT_EXCEEDED",
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send_text(json.dumps(limit_error_msg))
                        logger.warning(
                            f"Chat blocked due to subscription limit",
                            extra={
                                "tenant_id": tenant_id,
                                "session_id": session_id,
                                "reason": reason
                            }
                        )
                        continue
                except Exception as e:
                    # Log but continue on check error (fail open to prevent service disruption)
                    logger.error(
                        f"Failed to check subscription limits: {str(e)}",
                        extra={"tenant_id": tenant_id})
                t_usage = time.time()

                # Store user message
                user_msg_record = ChatMessage(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    message_type="user",
                    content=user_message,
                    message_metadata={"user_identifier": user_identifier}
                )
                self.db.add(user_msg_record)
                # Flush to generate ID but defer commit — batched with AI message below
                await asyncio.get_event_loop().run_in_executor(None, self.db.flush)

                t_store_user = time.time()

                # Publish user message event
                try:
                    asyncio.create_task(event_publisher.publish_message_created(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message_id=user_msg_record.id,
                        message_type="user",
                        content=user_message
                    ))
                except Exception as e:
                    # Log but don't fail on event publishing errors
                    print(f"Failed to publish user message event: {str(e)}")

                # Publish usage event and increment local cache (fire-and-forget)
                try:
                    asyncio.create_task(event_publisher.publish_chat_usage_event(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message_count=1
                    ))
                    # Optimistically increment local cache
                    usage_cache.increment_local_cache(tenant_id, message_count=1)
                except Exception as e:
                    # Log but don't fail on event publishing errors
                    logger.error(
                        "Failed to publish usage event",
                        extra={
                            "tenant_id": tenant_id,
                            "session_id": session_id,
                            "error": str(e),
                            "error_type": type(e).__name__
                        })

                # Detect mid-session token expiry
                if self._is_authenticated:
                    current_token = self._get_current_access_token(session_id)
                    if current_token is None:
                        self._is_authenticated = False
                        await websocket.send_text(json.dumps({
                            "type": "auth_expired",
                            "message": "Your authentication has expired. Please log in again."
                        }))
                        # Continue processing as guest

                # Check if tenant has any workflows at all (Redis-cached)
                try:
                    tenant_has_workflows = await self.workflow_client.has_workflows(tenant_id)
                except Exception:
                    tenant_has_workflows = True  # Fail open

                try:
                    response_msg = None
                    ai_response = None

                    if not tenant_has_workflows:
                        # Fast path: skip both workflow HTTP calls, go straight to AI
                        t_workflow_state = time.time()
                        t_trigger_or_step = t_workflow_state
                        timing_path = "ai"
                        ai_response = await self.chat_service.generate_response(
                            tenant_id=tenant_id,
                            user_message=user_message,
                            session_id=session_id,
                            tenant=tenant
                        )
                        t_ai = time.time()
                    else:
                        # Tenant has workflows — parallelize state check with vector pre-search
                        workflow_state_task = asyncio.create_task(
                            self.workflow_client.get_session_workflow_state(
                                tenant_id=tenant_id,
                                session_id=session_id
                            )
                        )
                        pre_search_task = asyncio.create_task(
                            self.chat_service.pre_search(
                                tenant_id=tenant_id,
                                user_message=user_message,
                                session_id=session_id,
                                tenant=tenant
                            )
                        )

                        workflow_state = await workflow_state_task
                        t_workflow_state = time.time()

                        # Check if workflow is completed - if so, treat as no active workflow
                        workflow_completed = False
                        if workflow_state:
                            variables = workflow_state.get("variables", {})
                            workflow_completed = variables.get("__workflow_completed", False)

                        if workflow_state and workflow_state.get("workflow_id") and not workflow_completed:
                            # Cancel pre_search — we're going down the workflow path
                            pre_search_task.cancel()
                            try:
                                await pre_search_task
                            except (asyncio.CancelledError, Exception):
                                pass

                            # Continue with existing workflow
                            waiting_for = workflow_state.get("waiting_for_input")
                            execution_id = workflow_state.get("execution_id")

                            if waiting_for == "choice":
                                workflow_result = await self.workflow_client.execute_workflow_step(
                                    tenant_id=tenant_id,
                                    session_id=session_id,
                                    execution_id=execution_id,
                                    user_choice=user_message,
                                    user_access_token=self._get_current_access_token(session_id)
                                )
                            else:
                                workflow_result = await self.workflow_client.execute_workflow_step(
                                    tenant_id=tenant_id,
                                    session_id=session_id,
                                    execution_id=execution_id,
                                    user_input=user_message,
                                    user_access_token=self._get_current_access_token(session_id)
                                )

                            t_trigger_or_step = time.time()
                            t_ai = t_trigger_or_step
                            timing_path = "workflow"

                            if not workflow_result.get("success", True):
                                error_message = workflow_result.get("error_message", "Workflow step failed")

                                if workflow_result.get("fallback_to_ai", False):
                                    logger.warning(f"Workflow step failed, falling back to AI: {error_message}", tenant_id=tenant_id)
                                    original_message = workflow_state.get("last_user_message") or user_message
                                    ai_response = await self.chat_service.generate_response(
                                        tenant_id=tenant_id,
                                        user_message=original_message,
                                        session_id=session_id,
                                        tenant=tenant
                                    )
                                    t_ai = time.time()
                                else:
                                    logger.error(f"Workflow step failed: {error_message}", tenant_id=tenant_id)
                                    ai_response = {
                                        "content": workflow_result.get("message", f"I encountered an error: {error_message}"),
                                        "metadata": {
                                            "workflow_step": True,
                                            "workflow_error": True,
                                            "error_message": error_message,
                                            "workflow_id": workflow_result.get("workflow_id"),
                                            "completed": True
                                        }
                                    }
                            else:
                                # Check if workflow completed with fallback to AI
                                if workflow_result.get("workflow_completed") and workflow_result.get("fallback_to_ai"):
                                    logger.info("Workflow completed with fallback to AI", tenant_id=tenant_id, session_id=session_id)
                                    # Use the original triggering message stored in workflow state,
                                    # not the current user_message (which is the choice text like "No thanks")
                                    original_message = workflow_state.get("last_user_message") or user_message
                                    ai_response = await self.chat_service.generate_response(
                                        tenant_id=tenant_id,
                                        user_message=original_message,
                                        session_id=session_id,
                                        tenant=tenant
                                    )
                                    t_ai = time.time()
                                    timing_path = "workflow->ai"
                                else:
                                    message = workflow_result.get("message") or ""
                                    choices = workflow_result.get("choices")

                                    ai_response = {
                                        "content": message,
                                        "metadata": {
                                            "workflow_step": True,
                                            "step_type": workflow_result.get("step_type"),
                                            "workflow_id": workflow_result.get("workflow_id"),
                                            "completed": workflow_result.get("workflow_completed", False),
                                            "choices": choices,
                                            "input_required": workflow_result.get("input_required")
                                        }
                                    }

                        else:
                            # No active workflow — check triggers
                            logger.info(f"Checking workflows for message: '{user_message[:50]}'", tenant_id=tenant_id, session_id=session_id)
                            trigger_result = await self.workflow_client.check_triggers(
                                tenant_id=tenant_id,
                                message=user_message,
                                session_id=session_id
                            )
                            logger.info(f"Workflow check result: triggered={trigger_result.get('triggered')}, workflow_id={trigger_result.get('workflow_id')}", tenant_id=tenant_id)

                            if trigger_result.get("triggered"):
                                # Cancel pre_search — we're starting a workflow
                                pre_search_task.cancel()
                                try:
                                    await pre_search_task
                                except (asyncio.CancelledError, Exception):
                                    pass

                                # Soft auth gate: if workflow requires auth and user is not authenticated
                                if trigger_result.get("requires_auth") and not self._is_authenticated:
                                    await websocket.send_text(json.dumps({
                                        "type": "auth_required",
                                        "message": "This feature requires you to log in first.",
                                        "workflow_name": trigger_result.get("workflow_name")
                                    }))
                                    ai_response = {
                                        "content": "This feature requires you to log in first.",
                                        "metadata": {"auth_required": True}
                                    }
                                    t_trigger_or_step = time.time()
                                    t_ai = t_trigger_or_step
                                    timing_path = "trigger->auth_required"
                                else:
                                    # Build user claims for variable injection
                                    user_claims = self._get_user_claims(session_id)

                                    execution_result = await self.workflow_client.start_workflow_execution(
                                        tenant_id=tenant_id,
                                        workflow_id=trigger_result["workflow_id"],
                                        session_id=session_id,
                                        user_message=user_message,
                                        user_access_token=self._get_current_access_token(session_id),
                                        user_claims=user_claims
                                    )

                                    t_trigger_or_step = time.time()

                                    first_step = execution_result.get("first_step_result", {})
                                    if not first_step.get("success", True):
                                        error_message = first_step.get("error_message", "Workflow failed to start")

                                        if first_step.get("fallback_to_ai", False):
                                            logger.warning(f"Workflow start failed, falling back to AI: {error_message}", tenant_id=tenant_id)
                                            ai_response = await self.chat_service.generate_response(
                                                tenant_id=tenant_id,
                                                user_message=user_message,
                                                session_id=session_id,
                                                tenant=tenant
                                            )
                                            t_ai = time.time()
                                            timing_path = "trigger->ai"
                                        else:
                                            logger.error(f"Workflow start failed: {error_message}", tenant_id=tenant_id)
                                            ai_response = {
                                                "content": first_step.get("message", f"I encountered an error: {error_message}"),
                                                "metadata": {
                                                    "workflow_step": True,
                                                    "workflow_error": True,
                                                    "error_message": error_message,
                                                    "completed": True
                                                }
                                            }
                                            t_ai = t_trigger_or_step
                                            timing_path = "trigger->workflow"
                                    else:
                                        # Check if first step completed workflow with fallback to AI
                                        if first_step.get("workflow_completed") and first_step.get("fallback_to_ai"):
                                            logger.info("Workflow start completed with fallback to AI", tenant_id=tenant_id, session_id=session_id)
                                            ai_response = await self.chat_service.generate_response(
                                                tenant_id=tenant_id,
                                                user_message=user_message,
                                                session_id=session_id,
                                                tenant=tenant
                                            )
                                            t_ai = time.time()
                                            timing_path = "trigger->ai"
                                        else:
                                            message = first_step.get("message") or "Workflow started"
                                            choices = first_step.get("choices")

                                            ai_response = {
                                                "content": message,
                                                "metadata": {
                                                    "workflow_triggered": True,
                                                    "workflow_id": trigger_result["workflow_id"],
                                                    "workflow_name": trigger_result.get("workflow_name"),
                                                    "execution_id": execution_result.get("id"),
                                                    "step_type": first_step.get("step_type"),
                                                    "choices": choices,
                                                    "input_required": first_step.get("input_required")
                                                }
                                            }
                                            t_ai = t_trigger_or_step
                                            timing_path = "trigger->workflow"
                            else:
                                # No workflow triggered — use pre-computed search results for AI
                                t_trigger_or_step = time.time()
                                pre_search_result = await pre_search_task
                                ai_response = await self.chat_service.generate_response(
                                    tenant_id=tenant_id,
                                    user_message=user_message,
                                    session_id=session_id,
                                    tenant=tenant,
                                    pre_search_result=pre_search_result
                                )
                                t_ai = time.time()
                                timing_path = "ai"

                    # Store AI/workflow response only if there's actual content
                    # Skip saving intermediate workflow transitions that don't have messages
                    if ai_response.get("content"):
                        ai_msg_record = ChatMessage(
                            tenant_id=tenant_id,
                            session_id=session_id,
                            message_type="assistant",
                            content=ai_response["content"],
                            message_metadata=ai_response.get("metadata", {})
                        )
                        self.db.add(ai_msg_record)
                        await asyncio.get_event_loop().run_in_executor(None, self.db.commit)

                        # Publish assistant message event with quality metrics
                        try:
                            asyncio.create_task(event_publisher.publish_message_created(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                message_id=ai_msg_record.id,
                                message_type="assistant",
                                content=ai_response["content"],
                                quality_metrics=ai_response.get("quality_metrics")
                            ))
                        except Exception as e:
                            # Log but don't fail on event publishing errors
                            print(f"Failed to publish assistant message event: {str(e)}")

                    if not ai_response.get("content"):
                        # No AI content to save — commit the flushed user message
                        await asyncio.get_event_loop().run_in_executor(None, self.db.commit)

                    # Only send response to client if there's content or choices to display
                    # This prevents blank messages from being shown to the user
                    metadata = ai_response.get("metadata", {})
                    if ai_response.get("content") or metadata.get("choices") or metadata.get("completed"):
                        # Send response to client
                        response_msg = {
                            "type": "message",
                            "role": "assistant",
                            "content": ai_response["content"],
                            "message_id": ai_msg_record.id if ai_response.get("content") else None,
                            "session_id": session_id,
                            "sources": ai_response.get("sources", []),
                            "metadata": ai_response.get("metadata", {}),
                            "timestamp": datetime.now().isoformat()
                        }

                        # Add choices at top level if present (for frontend display)
                        metadata = ai_response.get("metadata", {})
                        if metadata.get("choices"):
                            response_msg["choices"] = metadata["choices"]

                        await websocket.send_text(json.dumps(response_msg))
                    else:
                        print(f"DEBUG: Skipping empty message - no content or choices to display")

                    t_end = time.time()
                    logger.info(
                        "Chat message processed",
                        extra={
                            "tenant_id": tenant_id,
                            "session_id": session_id,
                            "total_ms": round((t_end - t_start) * 1000),
                            "usage_check_ms": round((t_usage - t_start) * 1000),
                            "store_user_ms": round((t_store_user - t_usage) * 1000),
                            "workflow_state_ms": round((t_workflow_state - t_store_user) * 1000),
                            "trigger_or_step_ms": round((t_trigger_or_step - t_workflow_state) * 1000),
                            "ai_response_ms": round((t_ai - t_trigger_or_step) * 1000),
                            "store_and_send_ms": round((t_end - t_ai) * 1000),
                            "path": timing_path,
                        }
                    )

                except Exception as e:
                    print(f"Error generating AI response: {str(e)}")  # Debug logging
                    import traceback
                    traceback.print_exc()  # Print full traceback for debugging
                    
                    error_msg = {
                        "type": "error",
                        "message": f"Failed to generate response: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send_text(json.dumps(error_msg))
        
        except WebSocketDisconnect:
            manager.disconnect(websocket, session_id)
            # Mark session as inactive
            chat_session.is_active = False
            await asyncio.get_event_loop().run_in_executor(None, self.db.commit)