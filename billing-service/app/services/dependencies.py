from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging
import os
import httpx
import jwt

from .redis_auth_cache import redis_token_cache
from .jwt_validator import jwt_validator
from .tenant_client import TenantClient

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


async def get_full_tenant_details(tenant_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetch full tenant details from the authorization server (checks cache first)"""

    # Try cache first (read-only, don't save to cache - OAuth server handles that)
    try:
        from ..services.cache_service import CacheService
        cache_service = CacheService()

        # Check cache first
        cached_tenant = cache_service.get_cached_tenant('id', tenant_id)
        if cached_tenant:
            logger.debug(f"Tenant details found in cache: {tenant_id}")
            return cached_tenant

        logger.debug(f"Tenant cache miss, fetching from auth server: {tenant_id}")
    except ImportError:
        logger.debug("Cache service not available, fetching from auth server")

    auth_server_url = os.environ.get("AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth")

    try:
        # Prepare headers
        headers = {"content-type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{auth_server_url}/api/v1/tenants/{tenant_id}",
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tenant not found"
                )

            if response.status_code != 200:
                logger.error(f"Failed to fetch tenant details: {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to fetch tenant details"
                )

            # OAuth server will cache the result, we just return it without caching
            tenant_data = response.json()
            logger.debug(f"Fetched tenant details from auth server: {tenant_id}")
            return tenant_data

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to authorization server: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authorization server unavailable"
        )


# API Key Authentication (for service-to-service calls)
tenant_client = TenantClient()


async def validate_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> TokenClaims:
    """Validate API key and return tenant claims (for service-to-service auth)"""

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key header missing",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    try:
        # Fetch tenant using API key
        tenant = await tenant_client.get_tenant_by_api_key(x_api_key)

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )

        # Create claims from tenant data (service account context)
        claims = TokenClaims(
            tenant_id=tenant["id"],
            user_id="service_account",  # API key auth doesn't have user context
            email=None,
            full_name=None,
            api_key=x_api_key,
            authorities=[]  # Service accounts have no user roles
        )

        logger.debug(f"API key validated for tenant: {tenant['id']}")
        return claims

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
    """
    Flexible authentication: accepts either JWT token OR API key.
    Use this for endpoints that need to support both user access (JWT) and service access (API key).
    """

    # Try JWT token first
    if credentials:
        try:
            return await validate_token(credentials)
        except HTTPException as e:
            # If JWT validation fails and no API key provided, raise the error
            if not x_api_key:
                raise

    # Try API key
    if x_api_key:
        return await validate_api_key(x_api_key)

    # Neither provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Bearer token or X-API-Key header",
        headers={"WWW-Authenticate": "Bearer, ApiKey"}
    )


# Backward compatibility aliases
get_current_tenant = validate_token
get_admin_tenant = require_admin
