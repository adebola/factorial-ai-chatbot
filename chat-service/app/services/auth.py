from typing import Optional, Dict, Any
from .tenant_client import TenantClient


class TenantAuthService:
    """Handle tenant authentication and authorization via onboarding service"""
    
    def __init__(self):
        self.tenant_client = TenantClient()

    async def authenticate_tenant_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Authenticate a tenant by JWT access token"""
        # Use the lookup endpoint that expects access tokens
        return await self.tenant_client.get_tenant_by_token(token)

    
    async def authenticate_tenant(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Authenticate tenant by API key via onboarding service"""
        return await self.tenant_client.get_tenant_by_api_key(api_key)
    
    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID via onboarding service"""
        return await self.tenant_client.get_tenant_by_id(tenant_id)
    
    def validate_tenant_access(self, tenant_id: str, requested_tenant_id: str) -> bool:
        """Ensure tenant can only access their own data"""
        return tenant_id == requested_tenant_id