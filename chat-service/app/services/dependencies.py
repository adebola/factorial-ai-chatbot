from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from dataclasses import dataclass
import jwt
import logging
import httpx
import os
import requests
from typing import Dict, Any

from ..services.oauth2_client import oauth2_client

logger = logging.getLogger(__name__)
# Configure HTTPBearer to return 401 instead of 403 for authentication failures
security = HTTPBearer(auto_error=False)


@dataclass
class TokenClaims:
    """Simple container for validated JWT token claims"""
    tenant_id: str
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    api_key: Optional[str] = None
    authorities: list = None
    access_token: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        if not self.authorities:
            return False
        return any(role in ["ROLE_ADMIN", "ADMIN", "ROLE_TENANT_ADMIN", "TENANT_ADMIN"]
                  for role in self.authorities)


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenClaims:
    """Validate OAuth2 token and extract claims"""

    # Check if credentials were provided
    if not credentials:
        logger.warning("No authorization credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    
    try:
        # Just validate token - don't fetch user info separately
        token_info = await oauth2_client.validate_token(token)
        
        # Extract required claims
        tenant_id = token_info.get("tenant_id")
        user_id = token_info.get("user_id") or token_info.get("sub")
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id claim",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id claim", 
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Create a claims object
        claims = TokenClaims(
            tenant_id=tenant_id,
            user_id=user_id,
            email=token_info.get("email"),
            full_name=token_info.get("full_name"),
            api_key=token_info.get("api_key"),
            authorities=token_info.get("authorities", []),
            # access_token=token  # Store the raw access token
        )
        
        logger.debug(f"Token validated for tenant: {tenant_id}, user: {user_id}")
        return claims
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def require_admin(
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    """Ensure the user has admin privileges"""
    
    if not claims.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return claims