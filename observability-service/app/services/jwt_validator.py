"""
Local JWT validation using RSA public keys from the authorization server.
"""
import os
import time
import json
import base64
import logging
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


@dataclass
class JWKSCache:
    """Cache for JSON Web Key Set."""
    keys: Dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0
    ttl_seconds: int = 3600

    def is_expired(self) -> bool:
        return time.time() - self.fetched_at > self.ttl_seconds


class LocalJWTValidator:
    """Validates JWTs locally using RSA public keys from the authorization server."""

    def __init__(self):
        self.auth_server_url = os.environ.get(
            "AUTHORIZATION_SERVER_URL", "http://localhost:9002/auth"
        )
        self.jwks_url = os.environ.get(
            "JWKS_URL", f"{self.auth_server_url}/oauth2/jwks"
        )
        self.issuer = os.environ.get("JWT_ISSUER", self.auth_server_url)
        self.jwks_cache = JWKSCache()
        self.public_keys: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self.verify_exp = True
        self.verify_aud = False
        self.leeway = 10

        logger.info(f"JWT Validator initialized with JWKS URL: {self.jwks_url}")

    async def _fetch_jwks(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
            jwks = response.json()
            logger.info(f"Fetched JWKS with {len(jwks.get('keys', []))} keys")
            return jwks

    def _jwk_to_public_key(self, jwk: Dict[str, Any]) -> Any:
        if jwk.get("kty") != "RSA":
            raise ValueError(f"Unsupported key type: {jwk.get('kty')}")
        return RSAAlgorithm.from_jwk(json.dumps(jwk))

    async def _refresh_keys(self) -> None:
        async with self._lock:
            if not self.jwks_cache.is_expired() and self.public_keys:
                return
            try:
                jwks = await self._fetch_jwks()
                new_keys = {}
                for jwk in jwks.get("keys", []):
                    kid = jwk.get("kid")
                    if kid:
                        try:
                            new_keys[kid] = self._jwk_to_public_key(jwk)
                        except Exception as e:
                            logger.error(f"Failed to load key {kid}: {e}")
                self.public_keys = new_keys
                self.jwks_cache = JWKSCache(keys=jwks.get("keys", []), fetched_at=time.time())
                logger.info(f"Refreshed {len(self.public_keys)} public keys")
            except Exception as e:
                logger.error(f"Failed to refresh keys: {e}")
                if not self.public_keys:
                    raise

    async def get_public_key(self, kid: Optional[str] = None) -> Any:
        if self.jwks_cache.is_expired() or not self.public_keys:
            await self._refresh_keys()
        if kid and kid in self.public_keys:
            return self.public_keys[kid]
        elif not kid and self.public_keys:
            return next(iter(self.public_keys.values()))
        else:
            await self._refresh_keys()
            if kid and kid in self.public_keys:
                return self.public_keys[kid]
            elif self.public_keys:
                return next(iter(self.public_keys.values()))
            raise ValueError(f"No public key found for kid: {kid}")

    def decode_token_header(self, token: str) -> Dict[str, Any]:
        try:
            header_segment = token.split('.')[0]
            header_segment += '=' * (4 - len(header_segment) % 4)
            return json.loads(base64.urlsafe_b64decode(header_segment))
        except Exception as e:
            logger.error(f"Failed to decode JWT header: {e}")
            raise ValueError("Invalid JWT format")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        header = self.decode_token_header(token)
        kid = header.get("kid")
        alg = header.get("alg", "RS256")

        public_key = await self.get_public_key(kid)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[alg],
            issuer=self.issuer,
            options={
                "verify_signature": True,
                "verify_exp": self.verify_exp,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": self.verify_aud,
                "require": ["exp", "iat", "iss", "sub"]
            },
            leeway=self.leeway
        )
        payload["active"] = True
        return payload


jwt_validator = LocalJWTValidator()
