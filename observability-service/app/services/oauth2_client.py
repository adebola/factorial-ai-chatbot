"""
OAuth2 service client for integrating with the authorization server.
"""
import os
import logging
from typing import Dict, Any

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class OAuth2ServiceClient:
    """Client for OAuth2 token validation via introspection."""

    def __init__(self):
        self.auth_server_url = os.environ.get(
            "AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth"
        )
        # Derive OAuth2 base URL (port 9000 for OAuth2 endpoints)
        self.oauth2_base_url = self.auth_server_url.replace(":9002/auth", ":9000")
        self.client_id = os.environ.get("OAUTH2_CLIENT_ID", "frontend-client")
        self.client_secret = os.environ.get("OAUTH2_CLIENT_SECRET", "secret")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate an access token via OAuth2 introspection."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.oauth2_base_url}/oauth2/introspect",
                    data={
                        "token": token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token validation failed"
                    )

                token_info = response.json()
                if not token_info.get("active", False):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token is not active"
                    )

                return token_info

        except HTTPException:
            raise
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except Exception as e:
            logger.error(f"Token introspection failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed"
            )


oauth2_client = OAuth2ServiceClient()
