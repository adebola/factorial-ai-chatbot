from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import timedelta

from ..core.database import get_db
from ..core.config import settings
from ..services.tenant_service import (
    TenantService, 
    TenantLogin, 
    ForgotPasswordRequest, 
    ResetPasswordRequest
)
from ..services.auth import AuthService
from ..core.logging_config import get_logger

router = APIRouter()

logger = get_logger("auth")


@router.post("/login")
async def login_tenant(
    login_data: TenantLogin,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Authenticate tenant and return JWT tokens"""

    logger.info(f"Login data: {login_data}")
    
    tenant_service = TenantService(db)
    tenant = tenant_service.authenticate_tenant(login_data)
    
    if not tenant:
        logger.error(f"Authentication failed for user {login_data.username} - tenant not found or invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create JWT tokens with enhanced claims
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={
            "sub": tenant.id,
            "user_id": tenant.id, 
            "username": tenant.username,
            "api_key": tenant.api_key
        }, 
        expires_delta=access_token_expires
    )
    refresh_token = AuthService.create_refresh_token(
        data={
            "sub": tenant.id,
            "user_id": tenant.id,
            "username": tenant.username
        }
    )

    logger.info(f" Login tenant {tenant.id} User: {login_data.username} Successful")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "tenant_id": tenant.id,
        "username": tenant.username
    }


@router.post("/forgot-password")
async def forgot_password(
    forgot_request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Request password reset token"""
    
    reset_token = AuthService.create_password_reset_token(db, forgot_request.email)
    
    if not reset_token:
        # Return success even if email doesn't exist (security practice)
        return {"message": "If the email exists, a password reset link has been sent"}
    
    # In a real application, you would send an email here
    # For now, we'll return the token (for testing purposes only)
    return {
        "message": "Password reset token generated",
        "reset_token": reset_token  # Remove this in production
    }


@router.post("/reset-password")
async def reset_password(
    reset_request: ResetPasswordRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Reset password using reset token"""
    
    success = AuthService.reset_password(
        db, 
        reset_request.token, 
        reset_request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    return {"message": "Password reset successfully"}