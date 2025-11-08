"""
Workflow service for CRUD operations and management.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from ..models.workflow_model import Workflow, WorkflowVersion, WorkflowTemplate, WorkflowStatus, TriggerType
from ..schemas.workflow_schema import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowSummary, WorkflowList,
    WorkflowTemplateCreate, WorkflowTemplateResponse
)
from ..core.exceptions import (
    WorkflowNotFoundError, WorkflowValidationError, TenantAccessError
)
from ..core.logging_config import get_logger
from .workflow_parser import WorkflowParser

logger = get_logger("workflow_service")


class WorkflowService:
    """Service for managing workflows"""

    def __init__(self, db: Session):
        self.db = db

    def create_workflow(
        self,
        workflow_data: WorkflowCreate,
        tenant_id: str,
        user_id: str
    ) -> WorkflowResponse:
        """
        Create a new workflow for a tenant.

        Args:
            workflow_data: Workflow creation data
            tenant_id: Tenant ID
            user_id: User ID creating the workflow

        Returns:
            Created workflow response
        """
        try:
            # Validate workflow definition
            errors = WorkflowParser.validate_workflow(workflow_data.definition)
            if errors:
                logger.error(f"Workflow create validation failed: {', '.join(errors)}")
                raise WorkflowValidationError(f"Workflow validation failed: {', '.join(errors)}")

            # Create workflow
            workflow = Workflow(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                name=workflow_data.name,
                description=workflow_data.description,
                definition=WorkflowParser.to_dict(workflow_data.definition),
                trigger_type=workflow_data.trigger_type,
                trigger_config=workflow_data.trigger_config,
                is_active=workflow_data.is_active,
                created_by=user_id,
                updated_by=user_id
            )

            self.db.add(workflow)
            self.db.commit()
            self.db.refresh(workflow)

            # Create initial version
            self._create_version(workflow, "Initial version", user_id)

            logger.info(f"Created workflow {workflow.id} for tenant {tenant_id}")
            return self._to_response(workflow)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create workflow: {e}")
            raise

    def get_workflow(self, workflow_id: str, tenant_id: str) -> WorkflowResponse:
        """
        Get a workflow by ID.

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            Workflow response

        Raises:
            WorkflowNotFoundError: If workflow not found
            TenantAccessError: If workflow doesn't belong to tenant
        """
        workflow = self.db.query(Workflow).filter(
            Workflow.id == workflow_id
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        if workflow.tenant_id != tenant_id:
            raise TenantAccessError(f"Workflow {workflow_id} does not belong to tenant {tenant_id}")

        return self._to_response(workflow)

    def list_workflows(
        self,
        tenant_id: str,
        page: int = 1,
        size: int = 10,
        status: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> WorkflowList:
        """
        List workflows for a tenant.

        Args:
            tenant_id: Tenant ID
            page: Page number (1-based)
            size: Page size
            status: Filter by status
            is_active: Filter by active status

        Returns:
            Paginated workflow list
        """
        query = self.db.query(Workflow).filter(Workflow.tenant_id == tenant_id)

        # Apply filters
        if status:
            query = query.filter(Workflow.status == status)
        if is_active is not None:
            query = query.filter(Workflow.is_active == is_active)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * size
        workflows = query.order_by(desc(Workflow.created_at)).offset(offset).limit(size).all()

        # Convert to summaries
        workflow_summaries = [self._to_summary(w) for w in workflows]

        return WorkflowList(
            workflows=workflow_summaries,
            total=total,
            page=page,
            size=size
        )

    def update_workflow(
        self,
        workflow_id: str,
        workflow_data: WorkflowUpdate,
        tenant_id: str,
        user_id: str
    ) -> WorkflowResponse:
        """
        Update a workflow.

        Args:
            workflow_id: Workflow ID
            workflow_data: Update data
            tenant_id: Tenant ID
            user_id: User ID updating the workflow

        Returns:
            Updated workflow response
        """
        workflow = self.db.query(Workflow).filter(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        try:
            # Track if definition changed for versioning
            definition_changed = False

            # Update fields
            if workflow_data.name is not None:
                workflow.name = workflow_data.name

            if workflow_data.description is not None:
                workflow.description = workflow_data.description

            if workflow_data.definition is not None:
                # Validate new definition
                errors = WorkflowParser.validate_workflow(workflow_data.definition)
                if errors:
                    logger.error(f"Workflow update validation failed: {', '.join(errors)}")
                    raise WorkflowValidationError(f"Workflow validation failed: {', '.join(errors)}")

                workflow.definition = WorkflowParser.to_dict(workflow_data.definition)
                definition_changed = True

            if workflow_data.trigger_type is not None:
                workflow.trigger_type = workflow_data.trigger_type

            if workflow_data.trigger_config is not None:
                workflow.trigger_config = workflow_data.trigger_config

            if workflow_data.is_active is not None:
                workflow.is_active = workflow_data.is_active

            if workflow_data.status is not None:
                workflow.status = workflow_data.status

            workflow.updated_by = user_id
            workflow.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(workflow)

            # Create a new version if definition changed
            if definition_changed:
                self._create_version(workflow, "Updated workflow definition", user_id)

            logger.info(f"Updated workflow {workflow_id}")
            return self._to_response(workflow)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update workflow {workflow_id}: {e}")
            raise

    def delete_workflow(self, workflow_id: str, tenant_id: str) -> bool:
        """
        Delete a workflow (soft delete).

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            True if deleted successfully
        """
        workflow = self.db.query(Workflow).filter(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        try:
            # Soft delete by setting status to archived
            workflow.status = WorkflowStatus.ARCHIVED.value
            workflow.is_active = False
            workflow.updated_at = datetime.utcnow()

            self.db.commit()

            logger.info(f"Deleted workflow {workflow_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete workflow {workflow_id}: {e}")
            raise

    def activate_workflow(self, workflow_id: str, tenant_id: str) -> WorkflowResponse:
        """
        Activate a workflow.

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            Updated workflow response
        """
        workflow = self.db.query(Workflow).filter(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        try:
            workflow.is_active = True
            workflow.status = WorkflowStatus.ACTIVE.value
            workflow.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(workflow)

            logger.info(f"Activated workflow {workflow_id}")
            return self._to_response(workflow)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to activate workflow {workflow_id}: {e}")
            raise

    def deactivate_workflow(self, workflow_id: str, tenant_id: str) -> WorkflowResponse:
        """
        Deactivate a workflow.

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            Updated workflow response
        """
        workflow = self.db.query(Workflow).filter(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        try:
            workflow.is_active = False
            workflow.status = WorkflowStatus.INACTIVE.value
            workflow.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(workflow)

            logger.info(f"Deactivated workflow {workflow_id}")
            return self._to_response(workflow)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to deactivate workflow {workflow_id}: {e}")
            raise

    def get_workflow_versions(self, workflow_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get version history for a workflow.

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            List of workflow versions
        """
        # Verify workflow exists and belongs to tenant
        workflow = self.db.query(Workflow).filter(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        ).first()

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        versions = self.db.query(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == workflow_id
        ).order_by(desc(WorkflowVersion.created_at)).all()

        return [
            {
                "id": version.id,
                "version": version.version,
                "change_summary": version.change_summary,
                "created_at": version.created_at,
                "created_by": version.created_by
            }
            for version in versions
        ]

    def create_template(
        self,
        template_data: WorkflowTemplateCreate,
        user_id: str
    ) -> WorkflowTemplateResponse:
        """
        Create a workflow template.

        Args:
            template_data: Template creation data
            user_id: User ID creating the template

        Returns:
            Created template response
        """
        try:
            # Validate workflow definition
            errors = WorkflowParser.validate_workflow(template_data.definition)
            if errors:
                logger.error(f"Workflow Template validation failed: {', '.join(errors)}")
                raise WorkflowValidationError(f"Template validation failed: {', '.join(errors)}")

            template = WorkflowTemplate(
                id=str(uuid.uuid4()),
                name=template_data.name,
                description=template_data.description,
                category=template_data.category,
                tags=template_data.tags,
                definition=WorkflowParser.to_dict(template_data.definition),
                default_config=template_data.default_config,
                is_public=template_data.is_public,
                created_by=user_id
            )

            self.db.add(template)
            self.db.commit()
            self.db.refresh(template)

            logger.info(f"Created workflow template {template.id}")
            return self._template_to_response(template)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create template: {e}")
            raise

    def list_templates(
        self,
        category: Optional[str] = None,
        is_public: Optional[bool] = True
    ) -> List[WorkflowTemplateResponse]:
        """
        List available workflow templates.

        Args:
            category: Filter by category
            is_public: Filter by public status

        Returns:
            List of templates
        """
        query = self.db.query(WorkflowTemplate)

        if category:
            query = query.filter(WorkflowTemplate.category == category)
        if is_public is not None:
            query = query.filter(WorkflowTemplate.is_public == is_public)

        templates = query.order_by(desc(WorkflowTemplate.usage_count)).all()

        return [self._template_to_response(t) for t in templates]

    def create_from_template(
        self,
        template_id: str,
        workflow_name: str,
        tenant_id: str,
        user_id: str,
        customization: Optional[Dict[str, Any]] = None
    ) -> WorkflowResponse:
        """
        Create a workflow from a template.

        Args:
            template_id: Template ID
            workflow_name: Name for the new workflow
            tenant_id: Tenant ID
            user_id: User ID
            customization: Custom configuration overrides

        Returns:
            Created workflow response
        """
        template = self.db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == template_id
        ).first()

        if not template:
            raise WorkflowNotFoundError(f"Template {template_id} not found")

        try:
            # Parse template definition
            definition = WorkflowParser.parse_from_dict(template.definition)

            # Apply customization if provided
            if customization:
                # Apply any custom trigger configuration
                trigger_config = customization.get("trigger_config", template.default_config or {})
            else:
                trigger_config = template.default_config or {}

            # Create workflow from template
            workflow_data = WorkflowCreate(
                name=workflow_name,
                description=template.description,
                definition=definition,
                trigger_type=definition.trigger.type,
                trigger_config=trigger_config,
                is_active=False  # Start inactive, user can activate manually
            )

            workflow = self.create_workflow(workflow_data, tenant_id, user_id)

            # Update template usage count
            template.usage_count += 1
            self.db.commit()

            logger.info(f"Created workflow {workflow.id} from template {template_id}")
            return workflow

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create workflow from template {template_id}: {e}")
            raise

    def _create_version(self, workflow: Workflow, change_summary: str, user_id: str) -> None:
        """Create a new version entry for a workflow"""
        # Auto-increment version number
        latest_version = self.db.query(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == workflow.id
        ).order_by(desc(WorkflowVersion.created_at)).first()

        if latest_version:
            # Parse version and increment
            try:
                parts = latest_version.version.split('.')
                minor = int(parts[1]) + 1
                new_version = f"{parts[0]}.{minor}.0"
            except (IndexError, ValueError):
                new_version = "1.1.0"
        else:
            new_version = "1.0.0"

        # Update workflow version
        workflow.version = new_version

        # Create version record
        version = WorkflowVersion(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            tenant_id=workflow.tenant_id,
            version=new_version,
            definition=workflow.definition,
            change_summary=change_summary,
            created_by=user_id
        )

        self.db.add(version)

    def _to_response(self, workflow: Workflow) -> WorkflowResponse:
        """Convert workflow model to response"""
        definition = WorkflowParser.parse_from_dict(workflow.definition)

        return WorkflowResponse(
            id=workflow.id,
            tenant_id=workflow.tenant_id,
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
            status=workflow.status,
            definition=definition,
            trigger_type=workflow.trigger_type,
            trigger_config=workflow.trigger_config,
            is_active=workflow.is_active,
            usage_count=workflow.usage_count,
            last_used_at=workflow.last_used_at,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            created_by=workflow.created_by,
            updated_by=workflow.updated_by
        )

    def _to_summary(self, workflow: Workflow) -> WorkflowSummary:
        """Convert workflow model to summary"""
        return WorkflowSummary(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            trigger_type=workflow.trigger_type,
            is_active=workflow.is_active,
            usage_count=workflow.usage_count,
            last_used_at=workflow.last_used_at,
            created_at=workflow.created_at
        )

    def _template_to_response(self, template: WorkflowTemplate) -> WorkflowTemplateResponse:
        """Convert template model to response"""
        definition = WorkflowParser.parse_from_dict(template.definition)

        return WorkflowTemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            category=template.category,
            tags=template.tags,
            definition=definition,
            default_config=template.default_config,
            is_public=template.is_public,
            usage_count=template.usage_count,
            rating=template.rating,
            created_at=template.created_at,
            updated_at=template.updated_at
        )