"""Workspace CRUD API — tenant-scoped."""
import logging
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.workspace import Workspace, WorkspaceDocument
from ..models.document import Document
from ..schemas.workspace import (
    WorkspaceCreate, WorkspaceUpdate, WorkspaceResponse,
    AddDocumentsRequest,
)
from ..schemas.document import DocumentListResponse
from ..services.dependencies import TokenClaims, validate_token

logger = logging.getLogger(__name__)
router = APIRouter()


def _workspace_response(ws: Workspace, db: Session) -> WorkspaceResponse:
    doc_count = db.query(WorkspaceDocument).filter(
        WorkspaceDocument.workspace_id == ws.id,
        WorkspaceDocument.removed_at.is_(None),
    ).count()
    return WorkspaceResponse(
        id=ws.id,
        tenant_id=ws.tenant_id,
        name=ws.name,
        description=ws.description,
        workspace_type=ws.workspace_type,
        status=ws.status,
        document_count=doc_count,
        is_archived=ws.is_archived,
        created_by=ws.created_by,
        created_by_email=ws.created_by_email,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    request: WorkspaceCreate,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = Workspace(
        tenant_id=claims.tenant_id,
        name=request.name,
        description=request.description,
        workspace_type=request.workspace_type,
        created_by=claims.user_id,
        created_by_email=claims.email,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    logger.info(f"Workspace '{ws.name}' created by {claims.email}")
    return _workspace_response(ws, db)


@router.get("/workspaces", response_model=List[WorkspaceResponse])
async def list_workspaces(
    include_archived: bool = False,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    q = db.query(Workspace).filter(Workspace.tenant_id == claims.tenant_id)
    if not include_archived:
        q = q.filter(Workspace.is_archived == False)
    workspaces = q.order_by(Workspace.created_at.desc()).all()
    return [_workspace_response(ws, db) for ws in workspaces]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.tenant_id == claims.tenant_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _workspace_response(ws, db)


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdate,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.tenant_id == claims.tenant_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    update = request.dict(exclude_unset=True)
    for k, v in update.items():
        setattr(ws, k, v)
    db.commit()
    db.refresh(ws)
    return _workspace_response(ws, db)


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def archive_workspace(
    workspace_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.tenant_id == claims.tenant_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws.is_archived = True
    ws.status = "archived"
    db.commit()


# ── Document membership ──

@router.get("/workspaces/{workspace_id}/documents", response_model=List[DocumentListResponse])
async def list_workspace_documents(
    workspace_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.tenant_id == claims.tenant_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    rows = (
        db.query(Document)
        .join(WorkspaceDocument, WorkspaceDocument.document_id == Document.id)
        .filter(
            WorkspaceDocument.workspace_id == workspace_id,
            WorkspaceDocument.removed_at.is_(None),
            Document.is_deleted == False,
        )
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [DocumentListResponse.model_validate(d) for d in rows]


@router.post("/workspaces/{workspace_id}/documents", status_code=201)
async def add_documents_to_workspace(
    workspace_id: str,
    request: AddDocumentsRequest,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.tenant_id == claims.tenant_id,
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    added = 0
    for doc_id in request.document_ids:
        doc = db.query(Document).filter(
            Document.id == doc_id,
            Document.tenant_id == claims.tenant_id,
            Document.is_deleted == False,
        ).first()
        if not doc:
            continue

        existing = db.query(WorkspaceDocument).filter(
            WorkspaceDocument.workspace_id == workspace_id,
            WorkspaceDocument.document_id == doc_id,
            WorkspaceDocument.removed_at.is_(None),
        ).first()
        if existing:
            continue

        wd = WorkspaceDocument(
            workspace_id=workspace_id,
            document_id=doc_id,
            added_by=claims.user_id,
        )
        db.add(wd)
        added += 1

    db.commit()
    return {"added": added}


@router.delete("/workspaces/{workspace_id}/documents/{document_id}", status_code=204)
async def remove_document_from_workspace(
    workspace_id: str,
    document_id: str,
    claims: TokenClaims = Depends(validate_token),
    db: Session = Depends(get_db),
):
    wd = db.query(WorkspaceDocument).filter(
        WorkspaceDocument.workspace_id == workspace_id,
        WorkspaceDocument.document_id == document_id,
        WorkspaceDocument.removed_at.is_(None),
    ).first()
    if not wd:
        raise HTTPException(status_code=404, detail="Document not in workspace")
    wd.removed_at = datetime.now(timezone.utc)
    wd.removed_by = claims.user_id
    db.commit()
