"""OAuth2 client for integrating with the authorization server"""
import os
import logging
from typing import Dict, Any, Optional
import httpx
from fastapi import HTTPException, status
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class OAuth2ServiceClient:
    """Client for interacting with the OAuth2 Authorization Server"""
    
    def __init__(self):
        self.auth_server_url = os.environ.get("AUTHORIZATION_SERVER_URL", "http://localhost:9000")
        self.client_id = os.environ.get("OAUTH2_CLIENT_ID", "factorialbot-client")
        self.client_secret = os.environ.get("OAUTH2_CLIENT_SECRET", "secret")
        self.timeout = 30.0
        
        # OAuth2 endpoints - properly append to base URL with context path
        # Note: urljoin replaces paths starting with /, so we need to append properly
        base_url = self.auth_server_url.rstrip('/')
        self.token_introspection_endpoint = f"{base_url}/oauth2/introspect"
        self.userinfo_endpoint = f"{base_url}/userinfo"
        self.token_endpoint = f"{base_url}/oauth2/token"
        
        logger.info(f"OAuth2 client initialized with server: {self.auth_server_url}")
        logger.debug(f"Token introspection endpoint: {self.token_introspection_endpoint}")
        logger.debug(f"UserInfo endpoint: {self.userinfo_endpoint}")
        logger.debug(f"Token endpoint: {self.token_endpoint}")
    
    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate an access token using OAuth2 token introspection
        
        Args:
            token: The access token to validate
            
        Returns:
            Token introspection response containing token details
            
        Raises:
            HTTPException: If token is invalid or validation fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_introspection_endpoint,
                    data={
                        "token": token,
                        "token_type_hint": "access_token"
                    },
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Token introspection failed: {response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token validation failed",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                token_info = response.json()
                
                # Check if token is active
                if not token_info.get("active", False):
                    logger.warning("Token is not active")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token is invalid or expired",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                return token_info
                
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation failed"
            )
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """
        Get user information from the OAuth2 userinfo endpoint
        
        Args:
            token: The access token
            
        Returns:
            User information from the authorization server
            
        Raises:
            HTTPException: If request fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.userinfo_endpoint,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json"
                    }
                )
                
                if response.status_code == 401:
                    logger.warning("Unauthorized access to userinfo endpoint")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get user info: {response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to retrieve user information"
                    )
                
                return response.json()
                
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user info: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve user information"
            )
    
    async def exchange_code_for_token(
        self, 
        code: str, 
        redirect_uri: str,
        code_verifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token
        
        Args:
            code: Authorization code
            redirect_uri: Redirect URI used in authorization request
            code_verifier: PKCE code verifier (optional)
            
        Returns:
            Token response containing access_token, refresh_token, etc.
            
        Raises:
            HTTPException: If token exchange fails
        """
        try:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            # Add PKCE code verifier if provided
            if code_verifier:
                data["code_verifier"] = code_verifier
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    error_data = response.json()
                    logger.error(f"Token exchange failed: {error_data}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_data.get("error_description", "Token exchange failed")
                    )
                
                return response.json()
                
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token exchange failed"
            )
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an access token using a refresh token
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            New token response
            
        Raises:
            HTTPException: If refresh fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_endpoint,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    error_data = response.json()
                    logger.error(f"Token refresh failed: {error_data}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token refresh failed",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                
                return response.json()
                
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token refresh failed"
            )
    
    async def revoke_token(self, token: str, token_type_hint: str = "access_token") -> bool:
        """
        Revoke a token
        
        Args:
            token: The token to revoke
            token_type_hint: Type of token (access_token or refresh_token)
            
        Returns:
            True if revocation was successful
            
        Raises:
            HTTPException: If revocation fails
        """
        try:
            revoke_endpoint = f"{self.auth_server_url.rstrip('/')}/oauth2/revoke"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    revoke_endpoint,
                    data={
                        "token": token,
                        "token_type_hint": token_type_hint
                    },
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                # According to RFC 7009, the server responds with HTTP 200 
                # regardless of whether the token was found or not
                return response.status_code == 200
                
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to authorization server: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization server unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token revocation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token revocation failed"
            )


# Create a singleton instance
oauth2_client = OAuth2ServiceClient()