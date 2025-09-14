from fastapi import APIRouter, WebSocket, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging_config import get_logger
from ..websockets.chat import ChatWebSocket

router = APIRouter()

logger = get_logger("ws")


@router.websocket("/ws/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    api_key: str = Query(None, description="Tenant API key"),
    tenant_id: str = Query(None, description="Tenant ID"),
    user_identifier: str = Query(None, description="Optional user identifier"),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for chat functionality (auth-free but requires tenant identification)"""
    logger.info(f"WebSocket endpoint: {websocket}")
    chat_ws = ChatWebSocket(db)
    await chat_ws.handle_connection(websocket, api_key, tenant_id, user_identifier)