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
from .redis_auth_cache import redis_token_cache
from .jwt_validator import jwt_validator

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
        """
        Check if user has tenant admin privileges.

        ROLE_TENANT_ADMIN: Organization/tenant-level admin
        """
        if not self.authorities:
            return False
        return "ROLE_TENANT_ADMIN" in self.authorities

    @property
    def is_system_admin(self) -> bool:
        """
        Check if user has SYSTEM_ADMIN privileges.

        ROLE_SYSTEM_ADMIN: Cross-tenant system admin (Factorial Systems staff)
        - Can view/manage all tenants
        - Bypasses tenant_id filtering
        - Full system-wide access
        """
        if not self.authorities:
            return False
        return "ROLE_SYSTEM_ADMIN" in self.authorities


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
        # Use local JWT validation for low latency
        # Falls back to introspection if needed
        token_info = await validate_jwt_locally(token)
        
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
            access_token=token  # Store the raw access token
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


async def require_system_admin(
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    """
    Ensure user has SYSTEM_ADMIN privileges.

    Raises:
        HTTPException 403: User lacks SYSTEM_ADMIN privileges
    """
    if not claims.is_system_admin:
        logger.warning(
            f"Unauthorized system admin access attempt - user_id: {claims.user_id}, authorities: {claims.authorities}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator privileges required"
        )

    logger.info(f"System admin access granted - user_id: {claims.user_id}")
    return claims


async def validate_jwt_locally(token: str) -> Dict[str, Any]:
    """
    Validate JWT token locally using cached RSA public keys.
    This provides sub-millisecond latency without network calls.
    """
    # Check Redis cache first (shared across all services)
    cached_info = await redis_token_cache.get(token)
    if cached_info:
        # Verify token is still active
        if cached_info.get("active", False):
            logger.debug("Using cached token validation from Redis")
            return cached_info

    # Cache miss - validate token locally
    try:
        # Use local JWT validation with RSA public keys
        token_info = await jwt_validator.validate_token(token)

        # Cache the validated token info in Redis for all services
        await redis_token_cache.set(token, token_info)

        return token_info

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        # Try fallback to introspection for resilience
        try:
            logger.info("Local validation failed, falling back to introspection")
            return await oauth2_client.validate_token(token)
        except Exception:
            # If introspection also fails, raise the original JWT error
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"}
            )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        # Try fallback to introspection
        try:
            logger.info("Local validation failed unexpectedly, falling back to introspection")
            return await oauth2_client.validate_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation failed"
            )