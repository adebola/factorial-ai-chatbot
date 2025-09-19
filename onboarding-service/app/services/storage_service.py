from minio import Minio
from minio.error import S3Error
from typing import BinaryIO, Optional
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin
from ..core.config import settings


class StorageService:
    """Service for managing file storage using MinIO/S3"""
    
    def __init__(self):
        # Get configuration from environment
        endpoint = os.environ.get("MINIO_ENDPOINT")
        access_key = os.environ.get("MINIO_ACCESS_KEY")
        secret_key = os.environ.get("MINIO_SECRET_KEY")
        secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
        region = os.environ.get("AWS_REGION", settings.AWS_REGION)

        if not all([endpoint, access_key, secret_key]):
            raise ValueError("Missing required S3/MinIO configuration: MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY")

        # Initialize MinIO client with proper error handling
        try:
            # For MinIO (not AWS S3), don't pass region unless explicitly needed
            if "amazonaws.com" in endpoint.lower():
                # This is AWS S3, use region
                self.client = Minio(
                    endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure,
                    region=region if region else None
                )
            else:
                # This is MinIO server, don't use region parameter
                self.client = Minio(
                    endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure
                )
        except Exception as e:
            raise ValueError(f"Failed to initialize S3/MinIO client: {e}")

        self.bucket_name = os.environ.get("MINIO_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("Missing required configuration: MINIO_BUCKET_NAME")

        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Create a bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error as e:
            print(f"Error creating bucket: {e}")
    
    def upload_file(
        self, 
        tenant_id: str, 
        file_data: BinaryIO, 
        filename: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """Upload file to the tenant's storage space"""
        
        # Generate unique filename with tenant prefix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(filename)[1]
        unique_filename = f"{timestamp}_{filename}"
        
        object_name = f"tenant_{tenant_id}/documents/{unique_filename}"
        
        try:
            # Upload file
            self.client.put_object(
                self.bucket_name,
                object_name,
                file_data,
                length=-1,  # Unknown length, MinIO will handle it
                content_type=content_type,
                part_size=10*1024*1024  # 10MB parts
            )
            
            return object_name
            
        except S3Error as e:
            # Log detailed error information for debugging
            error_details = {
                "code": e.code,
                "message": e.message,
                "resource": getattr(e, 'resource', 'unknown'),
                "request_id": getattr(e, 'request_id', 'unknown'),
                "host_id": getattr(e, 'host_id', 'unknown'),
                "bucket_name": self.bucket_name,
                "object_name": object_name,
                "endpoint": os.environ.get("MINIO_ENDPOINT"),
                "region": os.environ.get("AWS_REGION", settings.AWS_REGION),
                "secure": os.environ.get("MINIO_SECURE", "false")
            }
            print(f"S3 Upload Error Details: {error_details}")
            raise Exception(f"S3 operation failed; code: {e.code}, message: {e.message}, resource: {getattr(e, 'resource', 'unknown')}, request_id: {getattr(e, 'request_id', 'unknown')}, host_id: {getattr(e, 'host_id', 'unknown')}, bucket_name: {self.bucket_name}, object_name: {object_name}")
    
    def download_file(self, object_name: str) -> bytes:
        """Download file from storage"""
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            return response.read()
        except S3Error as e:
            raise Exception(f"Failed to download file: {str(e)}")
        finally:
            response.close()
            response.release_conn()
    
    def delete_file(self, object_name: str) -> bool:
        """Delete a file from storage"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            return True
        except S3Error as e:
            print(f"Error deleting file: {e}")
            return False
    
    def list_tenant_files(self, tenant_id: str) -> list:
        """List all files for a tenant"""
        try:
            prefix = f"tenant_{tenant_id}/documents/"
            objects = self.client.list_objects(
                self.bucket_name, 
                prefix=prefix, 
                recursive=True
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            print(f"Error listing files: {e}")
            return []
    
    def get_public_url(self, object_name: str, expires: timedelta = timedelta(days=7)) -> str:
        """Generate a presigned URL for public access to the file"""
        try:
            # For MinIO, generate presigned URL for GET operation
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            print(f"Error generating public URL: {e}")
            return ""
    
    def get_permanent_public_url(self, object_name: str) -> str:
        """
        Generate a permanent public URL (only works if bucket/object is set to public)
        For production, you should configure MinIO bucket policy for public read access
        """
        try:
            # Construct public URL manually
            minio_endpoint = os.environ.get("MINIO_ENDPOINT")
            # secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
            # protocol = "https" if secure else "http"
            
            # For direct access (requires public bucket policy)
            return f"{minio_endpoint}/{self.bucket_name}/{object_name}"
        except Exception as e:
            print(f"Error generating permanent public URL: {e}")
            return ""
    
    def upload_logo_file(
        self, 
        tenant_id: str, 
        file_data: BinaryIO, 
        filename: str,
        content_type: str
    ) -> tuple[str, str]:
        """
        Upload logo file and return both object name and public URL
        Returns: (object_name, public_url)
        """
        # Generate unique filename specifically for logos
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(filename)[1]
        unique_filename = f"logo{file_extension}"
        
        # Store in a logos subdirectory for better organization
        object_name = f"tenant_{tenant_id}/logos/{unique_filename}"
        
        try:
            # Upload file with cache control headers for logos
            self.client.put_object(
                self.bucket_name,
                object_name,
                file_data,
                length=-1,
                content_type=content_type,
                part_size=10*1024*1024,
                metadata={
                    'uploaded_at': timestamp,
                    'file_type': 'logo',
                    'tenant_id': tenant_id
                }
            )
            
            # Generate public URL (7 days expiry for presigned URLs)
            public_url = self.get_public_url(object_name, timedelta(days=7))
            
            return object_name, public_url
            
        except S3Error as e:
            raise Exception(f"Failed to upload logo file: {str(e)}")