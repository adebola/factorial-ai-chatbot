"""
Session Auth Service — Redis-based token storage for authenticated chat sessions.

Stores OAuth2 tokens (access_token, refresh_token) in Redis keyed by session_id.
Tokens are NOT stored in the database — only in Redis with TTL matching token expiry.
"""

import json
import httpx
import redis
import os
from typing import Optional, Dict, Any

from ..core.logging_config import get_logger

logger = get_logger("session_auth_service")


class SessionAuthService:
    """Manages end-user OAuth2 tokens for authenticated chat sessions."""

    REDIS_KEY_PREFIX = "session_auth:"

    def __init__(self):
        self.redis_client = redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )

    def _key(self, session_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}{session_id}"

    def store_tokens(
        self,
        session_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int,
        user_info: Dict[str, Any]
    ):
        """
        Store OAuth2 tokens in Redis tied to a session.

        Args:
            session_id: Chat session ID
            access_token: The user's access token from their IdP
            refresh_token: Optional refresh token
            expires_in: Token TTL in seconds
            user_info: Decoded user claims (sub, email, name)
        """
        data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_info": user_info,
            "expires_in": expires_in
        }
        # TTL = token expiry + 60s buffer for refresh
        ttl = expires_in + 60 if expires_in else 3600
        self.redis_client.setex(self._key(session_id), ttl, json.dumps(data))
        logger.info(
            "Stored auth tokens for session",
            session_id=session_id,
            user_sub=user_info.get("sub"),
            ttl=ttl
        )

    def get_access_token(self, session_id: str) -> Optional[str]:
        """Returns the stored access_token if still valid, None if expired/missing."""
        raw = self.redis_client.get(self._key(session_id))
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("access_token")

    def get_session_auth(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns the full auth data (tokens + user_info) for a session."""
        raw = self.redis_client.get(self._key(session_id))
        if not raw:
            return None
        return json.loads(raw)

    async def refresh_token(
        self,
        session_id: str,
        token_endpoint: str,
        client_id: str
    ) -> Optional[str]:
        """
        Use the stored refresh_token to get a new access_token.
        Updates Redis with new tokens.

        Returns:
            New access_token if refresh succeeded, None otherwise.
        """
        auth_data = self.get_session_auth(session_id)
        if not auth_data or not auth_data.get("refresh_token"):
            logger.warning("No refresh token available for session", session_id=session_id)
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    token_endpoint,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": auth_data["refresh_token"],
                        "client_id": client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

            if response.status_code != 200:
                logger.error(
                    "Token refresh failed",
                    session_id=session_id,
                    status=response.status_code,
                    body=response.text[:200]
                )
                return None

            token_data = response.json()
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", auth_data["refresh_token"])
            new_expires_in = token_data.get("expires_in", 3600)

            # Update stored tokens
            self.store_tokens(
                session_id=session_id,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_in=new_expires_in,
                user_info=auth_data.get("user_info", {})
            )

            logger.info("Token refreshed successfully", session_id=session_id)
            return new_access_token

        except Exception as e:
            logger.error("Token refresh error", session_id=session_id, error=str(e))
            return None

    def clear_tokens(self, session_id: str):
        """Remove tokens for a session (logout / session close)."""
        self.redis_client.delete(self._key(session_id))
        logger.info("Cleared auth tokens for session", session_id=session_id)

    # --- Pending auth workflow (survives WebSocket reconnection) ---

    _PENDING_KEY_PREFIX = "pending_auth_workflow:"

    def store_pending_workflow(self, session_id: str, user_message: str, workflow_id: str):
        """Store the message that triggered an auth-required workflow so it can be retried after login."""
        data = json.dumps({"user_message": user_message, "workflow_id": workflow_id})
        # TTL 10 minutes — if user hasn't logged in by then, discard
        self.redis_client.setex(f"{self._PENDING_KEY_PREFIX}{session_id}", 600, data)

    def pop_pending_workflow(self, session_id: str) -> Optional[Dict[str, str]]:
        """Retrieve and delete the pending workflow for a session. Returns None if nothing pending."""
        key = f"{self._PENDING_KEY_PREFIX}{session_id}"
        raw = self.redis_client.get(key)
        if not raw:
            return None
        self.redis_client.delete(key)
        return json.loads(raw)


# Singleton instance
session_auth_service = SessionAuthService()
