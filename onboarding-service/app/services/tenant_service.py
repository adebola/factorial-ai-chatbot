from sqlalchemy.orm import Session
from typing import Optional, List
import secrets
import string
import re
from email.utils import parseaddr
from pydantic import BaseModel
from ..models.tenant import Tenant, TenantRole, Plan
from .auth import AuthService
from .pg_vector_ingestion import PgVectorIngestionService
from ..core.database import get_vector_db


def is_valid_email(email: str) -> bool:
    """
    Lightweight email validation without external dependencies.
    - Uses parseaddr to ensure there's an address part
    - Applies a conservative regex for typical emails (local@domain.tld)
    """
    if not email or "@" not in email:
        return False
    # Ensure parseaddr extracts something that looks like an address
    _, addr = parseaddr(email)
    if not addr:
        return False
    # Conservative regex: local part + @ + domain with at least one dot and 2+ TLD chars
    email_regex = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
    return bool(email_regex.match(addr))


class TenantCreate(BaseModel):
    name: str
    domain: str
    username: str
    password: str
    email: Optional[str] = None
    website_url: Optional[str] = None
    role: TenantRole = TenantRole.USER


class TenantLogin(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class TenantService:
    """Service for managing tenant registration and configuration"""
    
    def __init__(self, db: Session):
        self.db = db
        # Get vector database session for vector ingestion service
        self.vector_db = next(get_vector_db())
        self.vector_ingestion_service = PgVectorIngestionService(db=self.vector_db)
    
    def generate_api_key(self) -> str:
        """Generate a secure API key for the tenant"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(64))
    
    def create_tenant(self, tenant_data: TenantCreate) -> Tenant:
        """Create a new tenant"""
        
        # Validate password
        if not AuthService.validate_password(tenant_data.password):
            raise ValueError(f"Password must be at least {AuthService.validate_password.__defaults__[0]} characters long")
        
        # Validate email format if provided
        if tenant_data.email is not None:
            if not is_valid_email(tenant_data.email):
                raise ValueError("Invalid email format")
        
        # Check if the domain already exists
        existing_domain = self.db.query(Tenant).filter(
            Tenant.domain == tenant_data.domain
        ).first()
        
        if existing_domain:
            raise ValueError(f"Domain {tenant_data.domain} is already registered")
        
        # Check if username already exists
        existing_username = self.db.query(Tenant).filter(
            Tenant.username == tenant_data.username
        ).first()
        
        if existing_username:
            raise ValueError(f"Username {tenant_data.username} is already taken")
        
        # Check if email already exists (if provided)
        if tenant_data.email:
            existing_email = self.db.query(Tenant).filter(
                Tenant.email == tenant_data.email
            ).first()
            
            if existing_email:
                raise ValueError(f"Email {tenant_data.email} is already registered")
        
        # Generate unique API key
        api_key = self.generate_api_key()
        while self.db.query(Tenant).filter(Tenant.api_key == api_key).first():
            api_key = self.generate_api_key()
        
        # Hash password
        password_hash = AuthService.get_password_hash(tenant_data.password)
        
        # Get the Free plan ID
        free_plan = self.db.query(Plan).filter(
            Plan.name == "Free",
            Plan.is_active == True,
            Plan.is_deleted == False
        ).first()
        
        if not free_plan:
            raise ValueError("Free plan not found. Please ensure default plans are created.")
        
        # Create tenant
        tenant = Tenant(
            name=tenant_data.name,
            domain=tenant_data.domain,
            username=tenant_data.username,
            password_hash=password_hash,
            email=tenant_data.email,
            role=tenant_data.role,
            website_url=tenant_data.website_url,
            api_key=api_key,
            plan_id=free_plan.id,
            is_active=True,
            config={}
        )
        
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        
        return tenant
    
    def get_tenant_by_id(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    def get_tenant_by_domain(self, domain: str) -> Optional[Tenant]:
        """Get tenant by domain"""
        return self.db.query(Tenant).filter(Tenant.domain == domain).first()
    
    def get_tenant_by_api_key(self, api_key: str) -> Optional[Tenant]:
        """Get tenant by API key"""
        return self.db.query(Tenant).filter(Tenant.api_key == api_key).first()
    
    def get_tenant_by_username(self, username: str) -> Optional[Tenant]:
        """Get tenant by username"""
        return self.db.query(Tenant).filter(Tenant.username == username).first()
    
    def get_tenant_by_email(self, email: str) -> Optional[Tenant]:
        """Get tenant by email"""
        return self.db.query(Tenant).filter(Tenant.email == email).first()
    
    def authenticate_tenant(self, login_data: TenantLogin) -> Optional[Tenant]:
        """Authenticate tenant with username and password"""
        return AuthService.authenticate_tenant(
            self.db, 
            login_data.username, 
            login_data.password
        )
    
    def update_tenant_config(self, tenant_id: str, config: dict) -> Tenant:
        """Update tenant configuration"""
        tenant = self.get_tenant_by_id(tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")
        
        tenant.config = {**tenant.config, **config}
        self.db.commit()
        self.db.refresh(tenant)
        
        return tenant
    
    def get_all_tenants(self, skip: int = 0, limit: int = 100) -> List[Tenant]:
        """Get all tenants (admin only operation)"""
        return self.db.query(Tenant).offset(skip).limit(limit).all()
    
    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant"""
        tenant = self.get_tenant_by_id(tenant_id)
        if not tenant:
            return False
        
        tenant.is_active = False
        self.db.commit()
        return True
    
    def delete_tenant(self, tenant_id: str) -> bool:
        """Completely delete a tenant and all associated data"""
        from ..models.tenant import Document, WebsiteIngestion, WebsitePage
        
        tenant = self.get_tenant_by_id(tenant_id)
        if not tenant:
            return False
        
        try:
            cleanup_results = {
                "vectors_deleted": False,
                "storage_files_deleted": 0,
                "pages_deleted": 0,
                "ingestions_deleted": 0,
                "documents_deleted": 0,
                "tenant_deleted": False
            }
            
            # Delete all files from storage for this tenant
            from .storage_service import StorageService
            storage_service = StorageService()
            tenant_files = storage_service.list_tenant_files(tenant_id)
            for file_path in tenant_files:
                if storage_service.delete_file(file_path):
                    cleanup_results["storage_files_deleted"] += 1
            print(f"✅ Deleted {cleanup_results['storage_files_deleted']} files from MinIO")
            
            # Delete all vectors for this tenant from PgVector
            vector_deleted = self.vector_ingestion_service.delete_tenant_vectors(tenant_id)

            cleanup_results["vectors_deleted"] = vector_deleted
            if vector_deleted:
                print(f"✅ Deleted all vectors from ChromaDB for tenant {tenant_id}")
            else:
                print(f"⚠️ Failed to delete vectors for tenant {tenant_id}")
            
            # Delete related data (foreign key cascade should handle this, but being explicit)
            # Delete website pages first (foreign key to ingestions)
            pages_deleted = self.db.query(WebsitePage).filter(WebsitePage.tenant_id == tenant_id).delete()
            cleanup_results["pages_deleted"] = pages_deleted
            print(f"✅ Deleted {pages_deleted} website pages")
            
            # Delete website ingestions
            ingestions_deleted = self.db.query(WebsiteIngestion).filter(WebsiteIngestion.tenant_id == tenant_id).delete()
            cleanup_results["ingestions_deleted"] = ingestions_deleted
            print(f"✅ Deleted {ingestions_deleted} website ingestions")
            
            # Delete documents
            documents_deleted = self.db.query(Document).filter(Document.tenant_id == tenant_id).delete()
            cleanup_results["documents_deleted"] = documents_deleted
            print(f"✅ Deleted {documents_deleted} documents")
            
            # Delete the tenant
            self.db.delete(tenant)
            cleanup_results["tenant_deleted"] = True
            self.db.commit()
            
            # Log cleanup summary
            print(f"📋 Tenant {tenant_id} deletion summary:")
            print(f"   - Storage Files (MinIO): ✅ {cleanup_results['storage_files_deleted']} files")
            print(f"   - Vectors (ChromaDB): {'✅' if cleanup_results['vectors_deleted'] else '❌'}")
            print(f"   - Website Pages: ✅ {cleanup_results['pages_deleted']} pages")
            print(f"   - Website Ingestions: ✅ {cleanup_results['ingestions_deleted']} ingestions")
            print(f"   - Documents: ✅ {cleanup_results['documents_deleted']} documents")
            print(f"   - Tenant Record: ✅")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Error deleting tenant {tenant_id}: {e}")
            return False