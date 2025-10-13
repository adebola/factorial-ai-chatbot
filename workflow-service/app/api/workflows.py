import logging
from typing import List, Any, Coroutine

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services.dependencies import TokenClaims, validate_token
from ..services.workflow_service import WorkflowService
from ..core.exceptions import (
    WorkflowNotFoundError, WorkflowValidationError, TenantAccessError
)
from ..core.logging_config import get_logger

from ..schemas.workflow_schema import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowList,
    WorkflowSummary, WorkflowTemplateResponse
)

router = APIRouter()
logger =  get_logger("workflow_api_controller")


@router.get("/", response_model=WorkflowList)
async def list_workflows(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: str = None,
    is_active: bool = None,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowList:
    """List workflows for the authenticated tenant"""
    try:
        service = WorkflowService(db)
        workflows = service.list_workflows(
            tenant_id=claims.tenant_id,
            page=page,
            size=size,
            status=status,
            is_active=is_active
        )

        logger.info("Workflows retrieved successfully")
        return workflows
    except Exception as e:
        logger.error(f"Error retrieving Workflows {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowResponse:
    """Get a specific workflow by ID"""
    try:
        service = WorkflowService(db)
        workflow = service.get_workflow(workflow_id, claims.tenant_id)
        logger.info(f"Single Workflow retrieved successfully {workflow_id}")
        return workflow
    except WorkflowNotFoundError:
        logger.error(f"Workflow Not found: {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    except TenantAccessError:
        logger.error(f"Tenant Access Error retrieving Workflow {workflow_id}")
        raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        logger.error(f"Exception retrieving Workflow {workflow_id}, {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(
    workflow: WorkflowCreate,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowResponse:
    """Create a new workflow"""
    try:
        service = WorkflowService(db)
        workflow = service.create_workflow(
            workflow_data=workflow,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id
        )
        logger.info(f"Workflow created successfully {workflow.id}")
        return workflow
    except WorkflowValidationError as e:
        logging.error(f"Error creating Workflow {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Exception creating Workflow: {str(e)}")
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
        workflow = service.update_workflow(
            workflow_id=workflow_id,
            workflow_data=workflow,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id
        )
        logger.info(f"Workflow updated successfully {workflow_id}")
        return  workflow
    except WorkflowNotFoundError:
        logger.error(f"WorkFlow {workflow_id} Not Found Updating Workflow")
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
) -> dict:
    """Delete a workflow"""
    try:
        service = WorkflowService(db)
        success = service.delete_workflow(workflow_id, claims.tenant_id)
        if success:
            return {"message": "Workflow deleted successfully"}
        else:
            logger.error(f"failed to delete Workflow {workflow_id}")
            raise HTTPException(status_code=500, detail="Failed to delete workflow")
    except WorkflowNotFoundError:
        logger.error(f"Workflow {workflow_id} delete NotFoundException {str(WorkflowNotFoundError)}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        logger.error(f"Workflow {workflow_id} delete UnknownException {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/activate", response_model=WorkflowResponse)
async def activate_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowResponse:
    """Activate a workflow"""
    try:
        service = WorkflowService(db)
        workflow = service.activate_workflow(workflow_id, claims.tenant_id)
        logger.info(f"Workflow {workflow_id} activated")
        return workflow
    except WorkflowNotFoundError:
        logger.error(f"Workflow Not Found, activating workflow {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        logger.error(f"Workflow {workflow_id} Activation Exception Raised: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/deactivate", response_model=WorkflowResponse)
async def deactivate_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowResponse:
    """Deactivate a workflow"""
    try:
        service = WorkflowService(db)
        workflow = service.deactivate_workflow(workflow_id, claims.tenant_id)
        logger.info(f"Workflow {workflow_id} deactivated")
        return workflow
    except WorkflowNotFoundError:
        logger.error(f"Workflow Not Found, deactivating workflow {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        logger.error(f"Workflow {workflow_id} DeActivation Exception Raised: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/versions")
async def get_workflow_versions(
    workflow_id: str,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> list[dict[str, Any]]:
    """Get version history for a workflow"""
    try:
        service = WorkflowService(db)
        ws = service.get_workflow_versions(workflow_id, claims.tenant_id)
        logger.info(f"Workflow Versions retrieved successfully {workflow_id}")
        return ws
    except WorkflowNotFoundError:
        logger.error(f"Workflow Versions for {workflow_id}, Not Found")
        raise HTTPException(status_code=404, detail="Workflow not found")
    except Exception as e:
        logger.error(f"Workflow Versions for {workflow_id}, Exception: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/list")
async def list_templates(
    category: str = None,
    db: Session = Depends(get_db)
) -> list[WorkflowTemplateResponse]:
    """List available workflow templates"""
    try:
        service = WorkflowService(db)
        ws = service.list_templates(category=category, is_public=True)
        logger.info("Workflow Templates retrieved successfully")
        return ws
    except Exception as e:
        logger.error(f"Workflow Templates Exception: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-template/{template_id}", response_model=WorkflowResponse)
async def create_from_template(
    template_id: str,
    workflow_name: str,
    customization: dict = None,
    db: Session = Depends(get_db),
    claims: TokenClaims = Depends(validate_token)
) -> WorkflowResponse:
    """Create a workflow from a template"""
    try:
        service = WorkflowService(db)
        workflow = service.create_from_template(
            template_id=template_id,
            workflow_name=workflow_name,
            tenant_id=claims.tenant_id,
            user_id=claims.user_id,
            customization=customization
        )
        logger.info(f"Create Workflow from Template {template_id} Success: {workflow_name}")
        return workflow
    except WorkflowNotFoundError:
        logger.error(f"Create Workflow from Template, Template Not Found {template_id}")
        raise HTTPException(status_code=404, detail="Template not found")
    except WorkflowValidationError as e:
        logger.error(f"Create Workflow from Template {template_id}, Workflow Validation Error {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create Workflow from Template {template_id}, Exception {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))