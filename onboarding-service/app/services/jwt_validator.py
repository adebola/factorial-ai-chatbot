"""
Local JWT validation using RSA public keys from the authorization server.
This provides low-latency token validation without network calls.
"""
import os
import time
import json
import base64
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import asyncio

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


@dataclass
class JWKSCache:
    """Cache for JSON Web Key Set"""
    keys: Dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0
    ttl_seconds: int = 3600  # Refresh keys every hour

    def is_expired(self) -> bool:
        """Check if the cached JWKS needs refresh"""
        return time.time() - self.fetched_at > self.ttl_seconds


class LocalJWTValidator:
    """
    Validates JWTs locally using RSA public keys from the authorization server.

    This approach provides:
    - Sub-millisecond validation latency
    - No network dependency for each request
    - Automatic key rotation handling
    - Resilience when auth server is down
    """

    def __init__(self):
        """Initialize the JWT validator"""
        self.auth_server_url = os.environ.get(
            "AUTHORIZATION_SERVER_URL",
            "http://localhost:9002/auth"
        )
        self.jwks_url = os.environ.get(
            "JWKS_URL",
            f"{self.auth_server_url}/oauth2/jwks"
        )
        self.issuer = os.environ.get(
            "JWT_ISSUER",
            self.auth_server_url
        )

        self.jwks_cache = JWKSCache()
        self.public_keys: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

        # Validation options
        self.verify_exp = True  # Verify expiration
        self.verify_aud = False  # Don't verify audience (varies per client)
        self.leeway = 10  # 10 seconds leeway for time claims

        logger.info(f"JWT Validator initialized with JWKS URL: {self.jwks_url}")

    async def _fetch_jwks(self) -> Dict[str, Any]:
        """
        Fetch the JSON Web Key Set from the authorization server.

        Returns:
            The JWKS as a dictionary
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()

                jwks = response.json()
                logger.info(f"Fetched JWKS with {len(jwks.get('keys', []))} keys")
                return jwks

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching JWKS: {e}")
            raise

    def _jwk_to_public_key(self, jwk: Dict[str, Any]) -> Any:
        """
        Convert a JWK to a public key object.

        Args:
            jwk: The JWK dictionary

        Returns:
            A public key object suitable for PyJWT
        """
        if jwk.get("kty") != "RSA":
            raise ValueError(f"Unsupported key type: {jwk.get('kty')}")

        # Use PyJWT's RSAAlgorithm to convert JWK to public key
        return RSAAlgorithm.from_jwk(json.dumps(jwk))

    async def _refresh_keys(self) -> None:
        """
        Refresh the cached public keys from JWKS.
        This is called automatically when keys are expired or missing.
        """
        async with self._lock:
            # Double-check after acquiring lock
            if not self.jwks_cache.is_expired() and self.public_keys:
                return

            try:
                jwks = await self._fetch_jwks()

                # Convert all JWKs to public keys
                new_keys = {}
                for jwk in jwks.get("keys", []):
                    kid = jwk.get("kid")
                    if kid:
                        try:
                            public_key = self._jwk_to_public_key(jwk)
                            new_keys[kid] = public_key
                            logger.debug(f"Loaded public key with kid: {kid}")
                        except Exception as e:
                            logger.error(f"Failed to load key {kid}: {e}")

                # Update cache
                self.public_keys = new_keys
                self.jwks_cache = JWKSCache(
                    keys=jwks.get("keys", []),
                    fetched_at=time.time()
                )

                logger.info(f"Refreshed {len(self.public_keys)} public keys")

            except Exception as e:
                logger.error(f"Failed to refresh keys: {e}")
                # Keep existing keys if refresh fails
                if not self.public_keys:
                    raise

    async def get_public_key(self, kid: Optional[str] = None) -> Any:
        """
        Get a public key for verification.

        Args:
            kid: Key ID from JWT header. If None, returns the first available key.

        Returns:
            The public key object
        """
        # Refresh keys if needed
        if self.jwks_cache.is_expired() or not self.public_keys:
            await self._refresh_keys()

        if kid and kid in self.public_keys:
            return self.public_keys[kid]
        elif not kid and self.public_keys:
            # Return the first available key
            return next(iter(self.public_keys.values()))
        else:
            # Try refreshing keys once more
            await self._refresh_keys()

            if kid and kid in self.public_keys:
                return self.public_keys[kid]
            elif self.public_keys:
                return next(iter(self.public_keys.values()))

            raise ValueError(f"No public key found for kid: {kid}")

    def decode_token_header(self, token: str) -> Dict[str, Any]:
        """
        Decode the JWT header without verification.

        Args:
            token: The JWT token string

        Returns:
            The decoded header as a dictionary
        """
        try:
            # Validate token format first
            if not token or not isinstance(token, str):
                raise ValueError("Token must be a non-empty string")

            # JWT tokens always start with "eyJ" (base64 of {"alg":...)
            if not token.startswith('eyJ'):
                logger.error(f"Invalid JWT format - token doesn't start with 'eyJ'. Got: {token[:50] if len(token) > 50 else token}")
                raise ValueError(f"Invalid JWT format - doesn't start with 'eyJ'")

            # Check for three parts separated by dots
            parts = token.split('.')
            if len(parts) != 3:
                logger.error(f"Invalid JWT format - expected 3 parts, got {len(parts)}")
                raise ValueError(f"Invalid JWT format - expected 3 parts, got {len(parts)}")

            # Split token and decode header
            header_segment = parts[0]
            # Add padding if needed
            header_segment += '=' * (4 - len(header_segment) % 4)
            header_bytes = base64.urlsafe_b64decode(header_segment)
            return json.loads(header_bytes)
        except ValueError:
            # Re-raise ValueError with our custom message
            raise
        except Exception as e:
            logger.error(f"Failed to decode JWT header: {e}")
            raise ValueError("Invalid JWT format")

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a JWT token locally using cached public keys.

        Args:
            token: The JWT token to validate

        Returns:
            The decoded and validated token payload

        Raises:
            jwt.ExpiredSignatureError: If the token is expired
            jwt.InvalidTokenError: If the token is invalid
            ValueError: If no suitable public key is found
        """
        try:
            # Decode header to get key ID
            header = self.decode_token_header(token)
            kid = header.get("kid")
            alg = header.get("alg", "RS256")

            logger.debug(f"Validating token with kid={kid}, alg={alg}")

            # Get the public key
            public_key = await self.get_public_key(kid)

            # Decode and verify the token
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

            logger.debug(f"Token validated successfully for subject: {payload.get('sub')}")

            # Add active flag for compatibility with introspection
            payload["active"] = True

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            raise

    async def validate_with_fallback(
        self,
        token: str,
        fallback_introspect=None
    ) -> Dict[str, Any]:
        """
        Validate token locally with optional fallback to introspection.

        This provides resilience: try fast local validation first,
        fall back to introspection if needed (e.g., for new keys).

        Args:
            token: The JWT token to validate
            fallback_introspect: Optional async function for introspection fallback

        Returns:
            The validated token claims
        """
        try:
            # Try local validation first
            return await self.validate_token(token)

        except (jwt.InvalidTokenError, ValueError) as e:
            if fallback_introspect:
                logger.info(f"Local validation failed ({e}), falling back to introspection")
                return await fallback_introspect(token)
            raise


# Global validator instance
jwt_validator = LocalJWTValidator()