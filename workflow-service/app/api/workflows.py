from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from ..core.database import get_db
from ..services.dependencies import TokenClaims, validate_token
from ..services.workflow_service import WorkflowService
from ..core.exceptions import (
    WorkflowNotFoundError, WorkflowValidationError, TenantAccessError
)
from ..schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowList,
    WorkflowSummary
)

router = APIRouter()


@router.get("/", response_model=WorkflowList)
async def list_workflows(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: str = None,
    is_active: bool = None,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """List workflows for the authenticated tenant"""
    try:
        service = WorkflowService(db)
        return service.list_workflows(
            tenant_id=claims.tenant_id,
            page=page,
            size=size,
            status=status,
            is_active=is_active
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Get a specific workflow by ID"""
    try:
        service = WorkflowService(db)
        return service.get_workflow(workflow_id, claims.tenant_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except TenantAccessError:
        raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(
    workflow: WorkflowCreate,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Create a new workflow"""
    try:
        service = WorkflowService(db)
        return service.create_workflow(
            workflow_data=workflow,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id
        )
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowUpdate,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Update a workflow"""
    try:
        service = WorkflowService(db)
        return service.update_workflow(
            workflow_id=workflow_id,
            workflow_data=workflow,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id
        )
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Delete a workflow"""
    try:
        service = WorkflowService(db)
        success = service.delete_workflow(workflow_id, claims.tenant_id)
        if success:
            return {"message": "Workflow deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete workflow")
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/activate", response_model=WorkflowResponse)
async def activate_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Activate a workflow"""
    try:
        service = WorkflowService(db)
        return service.activate_workflow(workflow_id, claims.tenant_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/deactivate", response_model=WorkflowResponse)
async def deactivate_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Deactivate a workflow"""
    try:
        service = WorkflowService(db)
        return service.deactivate_workflow(workflow_id, claims.tenant_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/versions")
async def get_workflow_versions(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Get version history for a workflow"""
    try:
        service = WorkflowService(db)
        return service.get_workflow_versions(workflow_id, claims.tenant_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/list")
async def list_templates(
    category: str = None,
    db: Session = Depends(get_db)
):
    """List available workflow templates"""
    try:
        service = WorkflowService(db)
        return service.list_templates(category=category, is_public=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-template/{template_id}", response_model=WorkflowResponse)
async def create_from_template(
    template_id: str,
    workflow_name: str,
    customization: dict = None,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
):
    """Create a workflow from a template"""
    try:
        service = WorkflowService(db)
        return service.create_from_template(
            template_id=template_id,
            workflow_name=workflow_name,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id,
            customization=customization
        )
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))