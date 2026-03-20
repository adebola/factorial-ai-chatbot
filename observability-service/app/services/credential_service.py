"""
AES-256 encryption/decryption for backend credentials.
"""
import os
import json
import base64
import logging
from typing import Dict, Any, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class CredentialService:
    """Encrypts and decrypts backend credentials using AES-256 (Fernet)."""

    def __init__(self):
        encryption_key = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        if encryption_key:
            # Derive a Fernet-compatible key from the provided key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"observability-service-salt",
                iterations=100_000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
            self._fernet = Fernet(key)
            logger.info("Credential encryption initialized")
        else:
            self._fernet = None
            logger.warning(
                "CREDENTIALS_ENCRYPTION_KEY not set - credentials will be stored as base64 only"
            )

    def encrypt(self, credentials: Dict[str, Any]) -> str:
        """Encrypt credentials dict to a string for storage."""
        json_bytes = json.dumps(credentials).encode("utf-8")
        if self._fernet:
            return self._fernet.encrypt(json_bytes).decode("utf-8")
        # Fallback: base64 encode (not secure, for dev only)
        return base64.urlsafe_b64encode(json_bytes).decode("utf-8")

    def decrypt(self, encrypted: str) -> Optional[Dict[str, Any]]:
        """Decrypt credentials string back to dict."""
        if not encrypted:
            return None
        try:
            if self._fernet:
                json_bytes = self._fernet.decrypt(encrypted.encode("utf-8"))
            else:
                json_bytes = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
            return json.loads(json_bytes)
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            return None


credential_service = CredentialService()
