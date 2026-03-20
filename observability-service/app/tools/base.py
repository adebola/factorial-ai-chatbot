"""
Base classes and configuration for observability tools.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict


@dataclass
class BackendConfig:
    """Configuration for connecting to an observability backend."""
    url: str
    auth_type: str = "none"  # none, basic, bearer, service_account
    credentials: Optional[Dict[str, Any]] = None
    verify_ssl: bool = True
    timeout_seconds: float = 10.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def get_headers(self) -> Dict[str, str]:
        """Build HTTP headers based on auth configuration."""
        headers = {"Content-Type": "application/json"}
        if self.auth_type == "bearer" and self.credentials:
            token = self.credentials.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "basic" and self.credentials:
            import base64
            username = self.credentials.get("username", "")
            password = self.credentials.get("password", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        return headers

    def get_auth_tuple(self) -> Optional[tuple]:
        """Get (username, password) tuple for basic auth."""
        if self.auth_type == "basic" and self.credentials:
            return (
                self.credentials.get("username", ""),
                self.credentials.get("password", "")
            )
        return None


class ObservabilityBaseTool(BaseTool):
    """Base class for observability tools with shared config."""
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)
