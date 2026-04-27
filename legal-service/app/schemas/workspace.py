from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    workspace_type: str = Field(default="project", pattern="^(project|shared_corpus)$")


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    workspace_type: str
    status: str
    document_count: int = 0
    is_archived: bool
    created_by: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AddDocumentsRequest(BaseModel):
    document_ids: List[str] = Field(..., min_length=1)


class RemoveDocumentRequest(BaseModel):
    document_id: str
