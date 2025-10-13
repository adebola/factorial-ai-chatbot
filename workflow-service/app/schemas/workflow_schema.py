from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class TriggerType(str, Enum):
    MESSAGE = "message"
    INTENT = "intent"
    KEYWORD = "keyword"
    MANUAL = "manual"


class StepType(str, Enum):
    MESSAGE = "message"
    CHOICE = "choice"
    INPUT = "input"
    CONDITION = "condition"
    ACTION = "action"
    SUB_WORKFLOW = "sub_workflow"
    DELAY = "delay"


# Workflow Step Schemas
class ChoiceOption(BaseModel):
    text: str
    value: str
    next_step: Optional[str] = None

class WorkflowStep(BaseModel):
    id: str
    type: StepType
    name: Optional[str] = None
    content: Optional[str] = None
    condition: Optional[str] = None
    options: Optional[List[ChoiceOption]] = None
    variable: Optional[str] = None
    action: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    next_step: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowTrigger(BaseModel):
    type: TriggerType
    conditions: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    intent_patterns: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    trigger: WorkflowTrigger
    steps: List[WorkflowStep]
    variables: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


# Request Schemas
class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    definition: WorkflowDefinition
    trigger_type: TriggerType
    trigger_config: Optional[Dict[str, Any]] = None
    is_active: bool = False


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    definition: Optional[WorkflowDefinition] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    status: Optional[WorkflowStatus] = None


# Response Schemas
class WorkflowResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    version: str
    status: WorkflowStatus
    definition: WorkflowDefinition
    trigger_type: TriggerType
    trigger_config: Optional[Dict[str, Any]]
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[str]
    updated_by: Optional[str]

    class Config:
        from_attributes = True


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: WorkflowStatus
    trigger_type: TriggerType
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowList(BaseModel):
    workflows: List[WorkflowSummary]
    total: int
    page: int
    size: int


# Template Schemas
class WorkflowTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    definition: WorkflowDefinition
    default_config: Optional[Dict[str, Any]] = None
    is_public: bool = False


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    definition: WorkflowDefinition
    default_config: Optional[Dict[str, Any]]
    is_public: bool
    usage_count: int
    rating: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Trigger Detection Schemas
class TriggerCheckRequest(BaseModel):
    message: str
    session_id: str
    user_context: Optional[Dict[str, Any]] = None


class TriggerCheckResponse(BaseModel):
    triggered: bool
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    confidence: float = 0.0
    trigger_type: Optional[TriggerType] = None
    metadata: Optional[Dict[str, Any]] = None