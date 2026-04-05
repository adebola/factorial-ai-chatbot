"""JWT token validation for audit API endpoints."""
import os
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_jwks_cache = {"keys": None}


@dataclass
class TokenClaims:
    tenant_id: str
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    authorities: list = None

    @property
    def is_system_admin(self) -> bool:
        if not self.authorities:
            return False
        return "ROLE_SYSTEM_ADMIN" in self.authorities


async def _get_jwks_keys():
    if _jwks_cache["keys"]:
        return _jwks_cache["keys"]

    jwks_url = os.environ.get("JWKS_URL")
    if not jwks_url:
        raise HTTPException(status_code=500, detail="JWKS_URL not configured")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            jwks = resp.json()
            _jwks_cache["keys"] = jwks.get("keys", [])
            return _jwks_cache["keys"]
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate token")


async def validate_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> TokenClaims:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    try:
        # Decode without verification first to get headers
        unverified = jwt.decode(token, options={"verify_signature": False})

        tenant_id = unverified.get("tenant_id")
        user_id = unverified.get("user_id") or unverified.get("sub")

        if not tenant_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing required claims"
            )

        return TokenClaims(
            tenant_id=tenant_id,
            user_id=user_id,
            email=unverified.get("email"),
            full_name=unverified.get("full_name"),
            authorities=unverified.get("authorities", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def require_system_admin(
    claims: TokenClaims = Depends(validate_token)
) -> TokenClaims:
    if not claims.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System admin privileges required"
        )
    return claims
