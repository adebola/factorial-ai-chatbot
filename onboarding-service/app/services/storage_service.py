from minio import Minio
from minio.error import S3Error
from typing import BinaryIO, Optional
import os
from datetime import datetime
from ..core.config import settings


class StorageService:
    """Service for managing file storage using MinIO/S3"""
    
    def __init__(self):
        self.client = Minio(
            os.environ.get("MINIO_ENDPOINT"),
            access_key=os.environ.get("MINIO_ACCESS_KEY"),
            secret_key=os.environ.get("MINIO_SECRET_KEY"),
            secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
            region=settings.AWS_REGION
        )
        self.bucket_name = os.environ.get("MINIO_BUCKET_NAME")
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
            raise Exception(f"Failed to upload file: {str(e)}")
    
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