"""
Base configuration for legal analysis tools.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class LegalToolConfig:
    """Runtime config passed to every legal tool instance."""
    tenant_id: str
    workspace_id: str
    access_token: Optional[str] = None
