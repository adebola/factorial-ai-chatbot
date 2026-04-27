from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    original_filename: str
    file_type: str
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    processing_status: str
    processing_error: Optional[str] = None
    content_hash: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_by_email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    processing_status: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
