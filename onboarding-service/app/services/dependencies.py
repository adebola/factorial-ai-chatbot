from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from dataclasses import dataclass
import jwt
import logging
import httpx
import os
import requests
from typing import Dict, Any

from ..services.oauth2_client import oauth2_client

logger = logging.getLogger(__name__)
security = HTTPBearer()


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
        """Check if user has admin privileges"""
        if not self.authorities:
            return False
        return any(role in ["ROLE_ADMIN", "ADMIN", "ROLE_TENANT_ADMIN", "TENANT_ADMIN"] 
                  for role in self.authorities)


async def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenClaims:
    """Validate OAuth2 token and extract claims"""
    
    token = credentials.credentials
    
    try:
        # Just validate token - don't fetch user info separately
        token_info = await oauth2_client.validate_token(token)
        
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


async def get_full_tenant_details(tenant_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetch full tenant details from the authorization server (checks cache first)"""
    
    # Try cache first (read-only, don't save to cache - OAuth server handles that)
    from ..services.cache_service import CacheService
    cache_service = CacheService()
    
    # Check cache first
    cached_tenant = cache_service.get_cached_tenant('id', tenant_id)
    if cached_tenant:
        logger.debug(f"Tenant details found in cache: {tenant_id}")
        return cached_tenant
    
    logger.debug(f"Tenant cache miss, fetching from auth server: {tenant_id}")
    
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


def get_tenant_settings(tenant_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """Get tenant settings from the OAuth2 server for widget customization"""
    try:
        # Get settings from OAuth2 server
        oauth2_server_url = os.getenv("AUTHORIZATION_SERVER_URL", "http://localhost:9000")
        settings_url = f"{oauth2_server_url}/api/v1/tenants/{tenant_id}/settings"
        
        # For now, we'll need a way to authenticate with the OAuth2 server
        # This is a service-to-service call, so we might need a service account token
        # For the migration, we'll use a fallback approach
        
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add authorization header if access token is provided
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        
        try:
            response = requests.get(settings_url, headers=headers, timeout=5)
            if response.status_code == 200:
                settings_data = response.json()
                return {
                    "primary_color": settings_data.get("primaryColor"),
                    "secondary_color": settings_data.get("secondaryColor"),
                    "company_logo_url": settings_data.get("companyLogoUrl"),
                    "chatLogo": settings_data.get("chatLogo"),  # New field with type, url, initials
                    "hover_text": settings_data.get("hoverText"),
                    "welcome_message": settings_data.get("welcomeMessage"),
                    "chat_window_title": settings_data.get("chatWindowTitle"),
                    "logo_url": settings_data.get("companyLogoUrl"),
                }
            else:
                logger.warning(f"Failed to fetch settings from OAuth2 server: {response.status_code}")
                return _get_fallback_settings()
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error connecting to OAuth2 server: {str(e)}")
            return _get_fallback_settings()
            
    except Exception as e:
        logger.warning(f"Could not load tenant settings for {tenant_id}: {str(e)}")
        return _get_fallback_settings()


def _get_fallback_settings() -> Dict[str, Any]:
    """Fallback to the local settings service if OAuth2 server is unavailable"""
    return {
        "primary_color": "#5D3EC1",
        "secondary_color": "#C15D3E",
        "company_logo_url": "https://",
        "hover_text": "AI Chat",
        "welcome_message": "Welcome to AI Chat",
        "chat_window_title": "Chat Support",
    }


# Backward compatibility aliases
get_current_tenant = validate_token
get_admin_tenant = require_admin