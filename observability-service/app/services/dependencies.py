"""
Authentication and authorization dependencies for the observability service.
"""
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from dataclasses import dataclass
import jwt
import logging
import httpx
import os

from .oauth2_client import oauth2_client
from .redis_auth_cache import redis_token_cache
from .jwt_validator import jwt_validator
from .tenant_client import TenantClient
from ..core.database import get_db

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@dataclass
class TokenClaims:
    """Container for validated JWT token claims."""
    tenant_id: str
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    api_key: Optional[str] = None
    authorities: list = None
    access_token: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        if not self.authorities:
            return False
        return "ROLE_TENANT_ADMIN" in self.authorities

    @property
    def is_system_admin(self) -> bool:
        if not self.authorities:
            return False
        return "ROLE_SYSTEM_ADMIN" in self.authorities


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenClaims:
    """Validate OAuth2 token and extract claims."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    try:
        token_info = await validate_jwt_locally(token)

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

        return TokenClaims(
            tenant_id=tenant_id,
            user_id=user_id,
            email=token_info.get("email"),
            full_name=token_info.get("full_name"),
            api_key=token_info.get("api_key"),
            authorities=token_info.get("authorities", []),
            access_token=token
        )

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
    """Ensure the user has admin privileges."""
    if not claims.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return claims


async def require_system_admin(
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    """Ensure user has SYSTEM_ADMIN privileges."""
    if not claims.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator privileges required"
        )
    return claims


async def validate_jwt_locally(token: str) -> Dict[str, Any]:
    """Validate JWT token locally using cached RSA public keys."""
    cached_info = await redis_token_cache.get(token)
    if cached_info:
        if cached_info.get("active", False):
            return cached_info

    try:
        token_info = await jwt_validator.validate_token(token)
        await redis_token_cache.set(token, token_info)
        return token_info
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        try:
            return await oauth2_client.validate_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"}
            )
    except Exception:
        try:
            return await oauth2_client.validate_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token validation failed"
            )


# API Key Authentication (for service-to-service calls)
tenant_client = TenantClient()


async def validate_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> TokenClaims:
    """Validate API key and return tenant claims."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key header missing",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    try:
        tenant = await tenant_client.get_tenant_by_api_key(x_api_key)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )

        return TokenClaims(
            tenant_id=tenant["id"],
            user_id="service_account",
            api_key=x_api_key,
            authorities=[]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )


async def validate_token_or_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> TokenClaims:
    """Flexible authentication: accepts either JWT token OR API key."""
    if credentials:
        try:
            return await validate_token(credentials)
        except HTTPException:
            if not x_api_key:
                raise

    if x_api_key:
        return await validate_api_key(x_api_key)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Bearer token or X-API-Key header",
        headers={"WWW-Authenticate": "Bearer, ApiKey"}
    )
