"""
JWT authentication and authorization for Answer Quality Service.

Uses local JWT validation with RSA public keys from the authorization server.
Provides FastAPI dependencies for token validation and admin access control.
"""

import os
from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.jwt_validator import LocalJWTValidator
from app.services.tenant_client import TenantClient
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Security scheme (auto_error=False to control status codes)
security = HTTPBearer(auto_error=False)

# Global JWT validator instance
jwt_validator = LocalJWTValidator()

# Tenant client for API key validation
tenant_client = TenantClient()


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Validate OAuth2 JWT token from Authorization header.

    Returns the decoded token claims (payload).

    Usage:
        @app.get("/protected")
        async def protected_endpoint(claims: dict = Depends(validate_token)):
            tenant_id = claims.get("tenant_id")
            user_id = claims.get("sub")
            ...

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    # Check if credentials were provided
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    try:
        # Validate token using local JWT validator
        payload = await jwt_validator.validate_token(token)

        # Ensure required claims are present
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing required claims (sub)",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Log successful authentication
        logger.debug(
            "Token validated successfully",
            user_id=payload.get("sub"),
            tenant_id=payload.get("tenant_id")
        )

        return payload

    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def require_admin(claims: dict = Depends(validate_token)) -> dict:
    """
    Require admin role for endpoint access.

    Usage:
        @app.get("/admin/dashboard")
        async def admin_dashboard(_: dict = Depends(require_admin)):
            # Only admins can access this endpoint
            ...

    Raises:
        HTTPException: 403 if user is not an admin
    """
    # Check if user has admin role
    roles = claims.get("roles", [])

    if isinstance(roles, str):
        roles = [roles]

    if "ROLE_ADMIN" not in roles and "admin" not in roles:
        logger.warning(
            "Admin access denied",
            user_id=claims.get("sub"),
            roles=roles
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return claims


def get_tenant_id(claims: dict) -> str:
    """
    Extract tenant_id from token claims.

    Usage:
        @app.get("/resource")
        async def get_resource(claims: dict = Depends(validate_token)):
            tenant_id = get_tenant_id(claims)
            ...

    Raises:
        HTTPException: 401 if tenant_id is missing from claims
    """
    tenant_id = claims.get("tenant_id")

    if not tenant_id:
        logger.error("Token missing tenant_id claim", claims=claims)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing tenant_id claim"
        )

    return tenant_id


def get_user_id(claims: dict) -> str:
    """
    Extract user_id (sub) from token claims.

    Usage:
        @app.get("/profile")
        async def get_profile(claims: dict = Depends(validate_token)):
            user_id = get_user_id(claims)
            ...

    Raises:
        HTTPException: 401 if user_id (sub) is missing from claims
    """
    user_id = claims.get("sub")

    if not user_id:
        logger.error("Token missing sub (user_id) claim", claims=claims)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim"
        )

    return user_id


async def validate_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Validate API key from X-API-Key header and return tenant_id.

    Used for widget endpoints where users are anonymous and don't have JWT tokens.

    Usage:
        @app.post("/widget/feedback")
        async def widget_feedback(tenant_id: str = Depends(validate_api_key)):
            # tenant_id is automatically extracted and validated
            ...

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header missing"
        )

    # Validate API key and get tenant
    tenant = await tenant_client.get_tenant_by_api_key(x_api_key)

    if not tenant:
        logger.warning(f"Invalid API key: {x_api_key[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    tenant_id = tenant.get("id")
    if not tenant_id:
        logger.error("Tenant data missing id field", tenant=tenant)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid tenant data"
        )

    logger.debug(f"API key validated for tenant: {tenant_id}")
    return tenant_id
