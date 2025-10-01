import yaml
import json
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from ..schemas.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger
from ..core.logging_config import get_logger

logger = get_logger("workflow_parser")


class WorkflowParseError(Exception):
    """Raised when workflow definition cannot be parsed"""
    pass


class WorkflowParser:
    """Parses and validates workflow definitions from YAML/JSON"""

    @staticmethod
    def parse_from_dict(definition: Dict[str, Any]) -> WorkflowDefinition:
        """Parse workflow definition from dictionary"""
        try:
            return WorkflowDefinition(**definition)
        except ValidationError as e:
            logger.error("Failed to parse workflow definition", error=str(e), definition=definition)
            raise WorkflowParseError(f"Invalid workflow definition: {e}")

    @staticmethod
    def parse_from_yaml(yaml_content: str) -> WorkflowDefinition:
        """Parse workflow definition from YAML string"""
        try:
            definition = yaml.safe_load(yaml_content)
            return WorkflowParser.parse_from_dict(definition)
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML content", error=str(e))
            raise WorkflowParseError(f"Invalid YAML format: {e}")

    @staticmethod
    def parse_from_json(json_content: str) -> WorkflowDefinition:
        """Parse workflow definition from JSON string"""
        try:
            definition = json.loads(json_content)
            return WorkflowParser.parse_from_dict(definition)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON content", error=str(e))
            raise WorkflowParseError(f"Invalid JSON format: {e}")

    @staticmethod
    def validate_workflow(definition: WorkflowDefinition) -> List[str]:
        """Validate workflow definition and return list of errors"""
        errors = []

        # Check for duplicate step IDs
        step_ids = [step.id for step in definition.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Duplicate step IDs found")

        # Validate step references
        for step in definition.steps:
            if step.next_step and step.next_step not in step_ids:
                errors.append(f"Step '{step.id}' references non-existent step '{step.next_step}'")

            # Validate condition steps have conditions
            if step.type == "condition" and not step.condition:
                errors.append(f"Condition step '{step.id}' missing condition expression")

            # Validate choice steps have options
            if step.type == "choice" and (not step.options or len(step.options) == 0):
                errors.append(f"Choice step '{step.id}' missing options")

            # Validate action steps have action type
            if step.type == "action" and not step.action:
                errors.append(f"Action step '{step.id}' missing action type")

        # Check for unreachable steps (no entry point)
        if definition.steps:
            first_step_id = definition.steps[0].id
            referenced_steps = set()

            for step in definition.steps:
                if step.next_step:
                    referenced_steps.add(step.next_step)

            # Find steps that are not the first step and not referenced by any other step
            unreachable = []
            for step in definition.steps[1:]:  # Skip first step
                if step.id not in referenced_steps:
                    unreachable.append(step.id)

            if unreachable:
                errors.append(f"Unreachable steps found: {', '.join(unreachable)}")

        return errors

    @staticmethod
    def get_first_step(definition: WorkflowDefinition) -> Optional[WorkflowStep]:
        """Get the first step in the workflow"""
        if not definition.steps:
            return None
        return definition.steps[0]

    @staticmethod
    def get_step_by_id(definition: WorkflowDefinition, step_id: str) -> Optional[WorkflowStep]:
        """Get a specific step by ID"""
        for step in definition.steps:
            if step.id == step_id:
                return step
        return None

    @staticmethod
    def get_next_step(definition: WorkflowDefinition, current_step: WorkflowStep) -> Optional[WorkflowStep]:
        """Get the next step after the current step"""
        if not current_step.next_step:
            return None
        return WorkflowParser.get_step_by_id(definition, current_step.next_step)

    @staticmethod
    def to_dict(definition: WorkflowDefinition) -> Dict[str, Any]:
        """Convert workflow definition to dictionary"""
        return definition.model_dump()

    @staticmethod
    def to_yaml(definition: WorkflowDefinition) -> str:
        """Convert workflow definition to YAML string"""
        return yaml.dump(WorkflowParser.to_dict(definition), default_flow_style=False, sort_keys=False)

    @staticmethod
    def to_json(definition: WorkflowDefinition) -> str:
        """Convert workflow definition to JSON string"""
        return json.dumps(WorkflowParser.to_dict(definition), indent=2)


# Example workflow definitions for testing
EXAMPLE_LEAD_QUALIFICATION = {
    "name": "Lead Qualification",
    "description": "Qualify potential leads and collect contact information",
    "trigger": {
        "type": "message",
        "conditions": ["pricing", "demo", "trial", "cost"]
    },
    "steps": [
        {
            "id": "greeting",
            "type": "message",
            "name": "Welcome Message",
            "content": "I'd love to help you learn more about our pricing! Let me ask a few questions to provide the best information.",
            "next_step": "company_size"
        },
        {
            "id": "company_size",
            "type": "choice",
            "name": "Company Size",
            "content": "What's your company size?",
            "options": ["1-10 employees", "11-50 employees", "51-200 employees", "200+ employees"],
            "variable": "company_size",
            "next_step": "use_case"
        },
        {
            "id": "use_case",
            "type": "input",
            "name": "Use Case",
            "content": "What's your primary use case for our platform?",
            "variable": "use_case",
            "next_step": "contact_check"
        },
        {
            "id": "contact_check",
            "type": "condition",
            "name": "Check if qualified",
            "condition": "company_size != '1-10 employees'",
            "next_step": "collect_email"
        },
        {
            "id": "collect_email",
            "type": "input",
            "name": "Collect Email",
            "content": "Great! I'd like to send you detailed pricing information. What's your email address?",
            "variable": "email",
            "next_step": "send_pricing"
        },
        {
            "id": "send_pricing",
            "type": "action",
            "name": "Send Pricing Email",
            "action": "send_email",
            "params": {
                "template": "pricing_info",
                "to": "{{email}}",
                "variables": {
                    "company_size": "{{company_size}}",
                    "use_case": "{{use_case}}"
                }
            }
        }
    ],
    "variables": {
        "company_size": "",
        "use_case": "",
        "email": ""
    }
}

EXAMPLE_SUPPORT_ESCALATION = {
    "name": "Support Escalation",
    "description": "Handle support requests and escalate when needed",
    "trigger": {
        "type": "message",
        "conditions": ["help", "support", "issue", "problem", "bug"]
    },
    "steps": [
        {
            "id": "greeting",
            "type": "message",
            "content": "Hi! I'm here to help. What type of issue are you experiencing?",
            "next_step": "issue_type"
        },
        {
            "id": "issue_type",
            "type": "choice",
            "content": "Please select the type of issue:",
            "options": ["Technical Problem", "Billing Question", "General Inquiry"],
            "variable": "issue_type",
            "next_step": "severity_check"
        },
        {
            "id": "severity_check",
            "type": "condition",
            "condition": "issue_type == 'Technical Problem'",
            "next_step": "collect_details"
        },
        {
            "id": "collect_details",
            "type": "input",
            "content": "Please describe the technical issue in detail:",
            "variable": "issue_details",
            "next_step": "create_ticket"
        },
        {
            "id": "create_ticket",
            "type": "action",
            "action": "create_support_ticket",
            "params": {
                "priority": "high",
                "category": "{{issue_type}}",
                "description": "{{issue_details}}"
            }
        }
    ]
}