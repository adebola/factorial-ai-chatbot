from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from ..core.database import get_db
from ..services.auth import AuthService
from ..models.tenant import Tenant, TenantRole

security = HTTPBearer()


def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Tenant:
    """Get current authenticated tenant from JWT token"""
    
    token = credentials.credentials
    tenant = AuthService.get_tenant_from_token(db, token)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return tenant


def get_admin_tenant(
    current_tenant: Tenant = Depends(get_current_tenant)
) -> Tenant:
    """Ensure the current tenant has admin role"""
    
    if current_tenant.role != TenantRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this operation"
        )
    
    return current_tenant


def get_current_tenant_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[Tenant]:
    """Get current tenant if token is provided, otherwise return None"""
    
    if not credentials:
        return None
    
    try:
        return get_current_tenant(credentials, db)
    except HTTPException:
        return None