"""
Authentication and authorization dependencies for the legal service.

Simplified from the observability-service pattern: uses only the local JWT
validator (no OAuth2 introspection fallback, no Redis token cache, no API key
auth). These can be added later if needed.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import jwt
import logging

from .jwt_validator import jwt_validator

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
    authorities: list = field(default_factory=list)
    access_token: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return "ROLE_TENANT_ADMIN" in (self.authorities or [])

    @property
    def is_system_admin(self) -> bool:
        return "ROLE_SYSTEM_ADMIN" in (self.authorities or [])


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenClaims:
    """Validate OAuth2 token and extract claims."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        token_info = await jwt_validator.validate_token(token)

        tenant_id = token_info.get("tenant_id")
        user_id = token_info.get("user_id") or token_info.get("sub")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id claim",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id claim",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return TokenClaims(
            tenant_id=tenant_id,
            user_id=user_id,
            email=token_info.get("email"),
            full_name=token_info.get("full_name"),
            api_key=token_info.get("api_key"),
            authorities=token_info.get("authorities", []),
            access_token=token,
        )

    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(
    claims: TokenClaims = Depends(validate_token),
) -> TokenClaims:
    if not claims.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return claims


async def require_system_admin(
    claims: TokenClaims = Depends(validate_token),
) -> TokenClaims:
    if not claims.is_system_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System administrator privileges required")
    return claims
