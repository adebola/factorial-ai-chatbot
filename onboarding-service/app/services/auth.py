from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import os
import secrets
import string

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.tenant import Tenant


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for handling authentication, JWT tokens, and password management"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def validate_password(password: str) -> bool:
        """Validate password meets minimum requirements"""
        return len(password) >= settings.PASSWORD_MIN_LENGTH
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
            )
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, 
            os.environ.get("JWT_SECRET_KEY"), 
            algorithm=os.environ.get("JWT_ALGORITHM", "HS256")
        )
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create a JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        )
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(
            to_encode,
            os.environ.get("JWT_SECRET_KEY"),
            algorithm=os.environ.get("JWT_ALGORITHM", "HS256")
        )
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(
                token, 
                os.environ.get("JWT_SECRET_KEY"), 
                algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")]
            )
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def authenticate_tenant(db: Session, username: str, password: str) -> Optional[Tenant]:
        """Authenticate a tenant with username and password"""
        tenant = db.query(Tenant).filter(Tenant.username == username).first()
        
        if not tenant:
            return None
        
        if not AuthService.verify_password(password, tenant.password_hash):
            return None
        
        if not tenant.is_active:
            return None
        
        return tenant
    
    @staticmethod
    def generate_reset_token() -> str:
        """Generate a secure password reset token"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))
    
    @staticmethod
    def create_password_reset_token(db: Session, email: str) -> Optional[str]:
        """Create a password reset token for a tenant"""
        tenant = db.query(Tenant).filter(Tenant.email == email).first()
        
        if not tenant:
            return None
        
        reset_token = AuthService.generate_reset_token()
        tenant.reset_token = reset_token
        tenant.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        db.commit()
        return reset_token
    
    @staticmethod
    def reset_password(db: Session, token: str, new_password: str) -> bool:
        """Reset tenant password using reset token"""
        tenant = db.query(Tenant).filter(Tenant.reset_token == token).first()
        
        if not tenant:
            return False
        
        if not tenant.reset_token_expires or tenant.reset_token_expires < datetime.now(timezone.utc):
            return False
        
        if not AuthService.validate_password(new_password):
            return False
        
        tenant.password_hash = AuthService.get_password_hash(new_password)
        tenant.reset_token = None
        tenant.reset_token_expires = None
        
        db.commit()
        return True
    
    @staticmethod
    def get_tenant_from_token(db: Session, token: str) -> Optional[Tenant]:
        """Get tenant from JWT token"""
        payload = AuthService.verify_token(token)
        
        if payload is None:
            return None
        
        tenant_id: str = payload.get("sub")
        if tenant_id is None:
            return None
        
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        return tenant


class TokenData:
    """Data class for token information"""
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id