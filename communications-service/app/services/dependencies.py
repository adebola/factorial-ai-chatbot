import os
import httpx
import logging
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ..core.logging_config import get_logger
from .redis_auth_cache import redis_token_cache
from .jwt_validator import jwt_validator

logger = get_logger("dependencies")
security = HTTPBearer(auto_error=False)

# OAuth2 introspection endpoint configuration
AUTH_SERVER_URL = os.environ.get("AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth")
TOKEN_INTROSPECT_URL = f"{AUTH_SERVER_URL}/oauth2/introspect"
OAUTH2_CLIENT_ID = os.environ.get("OAUTH2_CLIENT_ID", "webclient")
OAUTH2_CLIENT_SECRET = os.environ.get("OAUTH2_CLIENT_SECRET", "webclient-secret")


class TokenClaims(BaseModel):
    """JWT token claims"""
    user_id: str
    tenant_id: str
    email: str
    role: str = "user"
    exp: int


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed"
        )


async def introspect_token_fallback(token: str) -> Dict[str, Any]:
    """
    Fallback to OAuth2 token introspection endpoint.
    Used only when local validation fails (e.g., new keys not yet cached).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TOKEN_INTROSPECT_URL,
                data={
                    "token": token,
                    "token_type_hint": "access_token"
                },
                auth=(OAUTH2_CLIENT_ID, OAUTH2_CLIENT_SECRET),
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
        logger.error(f"Unexpected error during token introspection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed"
        )


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenClaims:
    """Validate JWT token and extract claims"""

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    # Use local JWT validation for low latency with fallback to introspection
    try:
        token_info = await validate_jwt_locally(token)
    except Exception as jwt_error:
        logger.warning(f"Local JWT validation failed: {jwt_error}, falling back to introspection")
        token_info = await introspect_token_fallback(token)

    # Extract required claims from introspection response
    try:
        # The introspection response contains the token claims
        user_id = token_info.get("user_id") or token_info.get("sub")
        tenant_id = token_info.get("tenant_id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id claim",
                headers={"WWW-Authenticate": "Bearer"}
            )

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id claim",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Extract authorities and determine role
        # Current role: ROLE_TENANT_ADMIN (tenant/organization admin)
        # Future role: ROLE_SYSTEM_ADMIN (system-wide admin, not yet implemented)
        authorities = token_info.get("authorities", [])
        role = "user"
        if "ROLE_TENANT_ADMIN" in authorities:
            role = "admin"

        claims = TokenClaims(
            user_id=user_id,
            tenant_id=tenant_id,
            email=token_info.get("email", ""),
            role=role,
            exp=token_info.get("exp", 0)
        )

        logger.debug(f"Token validated for tenant: {tenant_id}, user: {user_id}")
        return claims

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract token claims: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token structure",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def validate_super_admin_token(
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    """Validate that the token belongs to a super admin"""

    if claims.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )

    return claims


def check_tenant_access(tenant_id: str, claims: TokenClaims) -> bool:
    """Check if user has access to the specified tenant"""
    # Super admins can access any tenant
    if claims.role == "super_admin":
        return True

    # Regular users can only access their own tenant
    return claims.tenant_id == tenant_id


async def validate_tenant_access(
    tenant_id: str,
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    """Validate that the user has access to the specified tenant"""

    if not check_tenant_access(tenant_id, claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this tenant"
        )

    return claims