from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
import json
import uuid
from datetime import datetime

from ..core.database import get_db
from ..models.chat_models import ChatSession, ChatMessage
from ..services.chat_service import ChatService
from ..services.tenant_client import TenantClient
from ..services.workflow_client import WorkflowClient


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
    
    async def handle_connection(self, websocket: WebSocket, api_key: str = None, tenant_id: str = None, user_identifier: str = None):
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

        # Create or get a chat session
        session_id = str(uuid.uuid4())
        tenant_id = tenant["id"]  # tenant is now a dict from HTTP API
        chat_session = ChatSession(
            tenant_id=tenant_id,
            session_id=session_id,
            user_identifier=user_identifier,
            is_active=True
        )
        self.db.add(chat_session)
        self.db.commit()
        
        await manager.connect(websocket, tenant_id, session_id)
        
        try:
            # Send a welcome message
            welcome_msg = {
                "type": "connection",
                "session_id": session_id,
                "message": "Connected to chat service",
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(welcome_msg))
            
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
                
                # Store user message
                user_msg_record = ChatMessage(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    message_type="user",
                    content=user_message,
                    message_metadata={"user_identifier": user_identifier}
                )
                self.db.add(user_msg_record)
                self.db.commit()

                # Check if there's an active workflow for this session
                try:
                    workflow_state = await self.workflow_client.get_session_workflow_state(
                        tenant_id=tenant_id,
                        session_id=session_id
                    )

                    response_msg = None
                    ai_response = None

                    # Check if workflow is completed - if so, treat as no active workflow
                    workflow_completed = False
                    if workflow_state:
                        variables = workflow_state.get("variables", {})
                        workflow_completed = variables.get("__workflow_completed", False)

                    if workflow_state and workflow_state.get("workflow_id") and not workflow_completed:
                        # Continue with existing workflow
                        # Check if workflow is waiting for a choice
                        waiting_for = workflow_state.get("waiting_for_input")
                        execution_id = workflow_state.get("execution_id")

                        if waiting_for == "choice":
                            # Send as choice selection
                            workflow_result = await self.workflow_client.execute_workflow_step(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                execution_id=execution_id,
                                user_choice=user_message
                            )
                        else:
                            # Send as regular input
                            workflow_result = await self.workflow_client.execute_workflow_step(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                execution_id=execution_id,
                                user_input=user_message
                            )

                        if workflow_result.get("error"):
                            # Workflow execution failed, fall back to AI
                            ai_response = await self.chat_service.generate_response(
                                tenant_id=tenant_id,
                                user_message=user_message,
                                session_id=session_id
                            )
                        else:
                            # Extract message and choices from workflow step result
                            message = workflow_result.get("message", "")
                            choices = workflow_result.get("choices")

                            # Format workflow response
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
                        # Check if message triggers any workflows
                        trigger_result = await self.workflow_client.check_triggers(
                            tenant_id=tenant_id,
                            message=user_message,
                            session_id=session_id
                        )

                        if trigger_result.get("triggered"):
                            # Start workflow execution
                            execution_result = await self.workflow_client.start_workflow_execution(
                                tenant_id=tenant_id,
                                workflow_id=trigger_result["workflow_id"],
                                session_id=session_id
                            )

                            if execution_result.get("error"):
                                # Workflow start failed, fall back to AI
                                ai_response = await self.chat_service.generate_response(
                                    tenant_id=tenant_id,
                                    user_message=user_message,
                                    session_id=session_id
                                )
                            else:
                                # Extract message from first step result
                                first_step = execution_result.get("first_step_result", {})
                                message = first_step.get("message", "Workflow started")
                                choices = first_step.get("choices")

                                # Format workflow response
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
                        else:
                            # No workflow triggered, use AI response
                            ai_response = await self.chat_service.generate_response(
                                tenant_id=tenant_id,
                                user_message=user_message,
                                session_id=session_id
                            )

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
                        self.db.commit()

                    # Only send response to client if there's content or choices to display
                    # This prevents blank messages from being shown to the user
                    if ai_response.get("content") or ai_response.get("metadata", {}).get("choices"):
                        # Send response to client
                        response_msg = {
                            "type": "message",
                            "role": "assistant",
                            "content": ai_response["content"],
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
            self.db.commit()