import re
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from ..models.workflow_model import Workflow, TriggerType
from ..schemas.workflow_schema import TriggerCheckResponse
from ..core.logging_config import get_logger, log_workflow_trigger

logger = get_logger("trigger_detector")


def _check_message_trigger(workflow: Workflow, message: str) -> float:
    """
    Check message-based triggers

    Message triggers check for phrase/substring matches in the user's message.
    They look in both 'conditions' and 'keywords' arrays for backward compatibility.
    """
    trigger_config = workflow.trigger_config or {}
    conditions = trigger_config.get("conditions", [])
    keywords = trigger_config.get("keywords", [])

    # Combine both conditions and keywords for checking
    phrases_to_check = conditions + keywords

    if not phrases_to_check:
        return 0.0

    message_lower = message.lower().strip()
    matches = 0
    total_phrases = len(phrases_to_check)

    for phrase in phrases_to_check:
        if isinstance(phrase, str):
            phrase_lower = phrase.lower().strip()
            # Check if phrase exists in message (substring or exact match)
            if phrase_lower in message_lower or message_lower in phrase_lower:
                matches += 1

    if matches == 0:
        return 0.0

    # Calculate confidence based on match ratio and message length
    match_ratio = matches / total_phrases

    # Bonus for multiple matches in shorter messages
    message_length_factor = min(1.0, 50 / len(message)) if len(message) > 0 else 0.0

    confidence = (match_ratio * 0.7) + (message_length_factor * 0.3)
    return min(1.0, confidence)


class TriggerDetector:
    """Detects when user messages should trigger workflows"""

    def __init__(self, db: Session):
        self.db = db

    async def check_triggers(
        self,
        tenant_id: str,
        message: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> TriggerCheckResponse:
        """Check if message should trigger any workflows for the tenant"""

        # Get active workflows for tenant
        active_workflows = self.db.query(Workflow).filter(
            Workflow.tenant_id == tenant_id,
            Workflow.is_active == True,
            Workflow.status == "active"
        ).all()

        if not active_workflows:
            log_workflow_trigger(
                tenant_id=tenant_id,
                trigger_type="none",
                message=message,
                triggered=False,
                reason="no_active_workflows"
            )
            return TriggerCheckResponse(triggered=False)

        # Check each workflow for triggers
        best_match = None
        highest_confidence = 0.0

        for workflow in active_workflows:
            confidence = self._calculate_trigger_confidence(workflow, message, user_context)

            if confidence > highest_confidence and confidence > 0.5:  # Minimum confidence threshold
                highest_confidence = confidence
                best_match = workflow

        if best_match:
            log_workflow_trigger(
                tenant_id=tenant_id,
                trigger_type=best_match.trigger_type.value,
                message=message,
                triggered=True,
                workflow_id=best_match.id,
                workflow_name=best_match.name,
                confidence=highest_confidence
            )

            return TriggerCheckResponse(
                triggered=True,
                workflow_id=best_match.id,
                workflow_name=best_match.name,
                confidence=highest_confidence,
                trigger_type=best_match.trigger_type,
                metadata={
                    "trigger_config": best_match.trigger_config,
                    "workflow_version": best_match.version
                }
            )
        else:
            log_workflow_trigger(
                tenant_id=tenant_id,
                trigger_type="none",
                message=message,
                triggered=False,
                reason="no_triggers_matched",
                workflows_checked=len(active_workflows)
            )

            return TriggerCheckResponse(triggered=False)

    def _calculate_trigger_confidence(
        self,
        workflow: Workflow,
        message: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> float:
        """Calculate confidence score for workflow trigger (0.0 to 1.0)"""

        if workflow.trigger_type == TriggerType.MESSAGE:
            return _check_message_trigger(workflow, message)
        elif workflow.trigger_type == TriggerType.KEYWORD:
            return self._check_keyword_trigger(workflow, message)
        elif workflow.trigger_type == TriggerType.INTENT:
            return self._check_intent_trigger(workflow, message, user_context)
        elif workflow.trigger_type == TriggerType.MANUAL:
            return 0.0  # Manual triggers are not automatic
        else:
            return 0.0

    @staticmethod
    def _check_keyword_trigger(workflow: Workflow, message: str) -> float:
        """Check keyword-based triggers, search for the keyword in the message"""
        trigger_config = workflow.trigger_config or {}
        keywords = trigger_config.get("keywords", [])

        if not keywords:
            return 0.0

        message_lower = message.lower()
        matches = 0

        for keyword in keywords:
            if isinstance(keyword, str):
                # Exact word match (not just substring)
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, message_lower):
                    matches += 1

        if matches == 0:
            return 0.0

        # Higher confidence for more keyword matches
        confidence = min(1.0, matches / len(keywords) * 1.2)
        return confidence

    @staticmethod
    def _check_intent_trigger(
        workflow: Workflow,
        message: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> float:
        """Check intent-based triggers (simplified implementation)"""
        trigger_config = workflow.trigger_config or {}
        intent_patterns = trigger_config.get("intent_patterns", [])

        if not intent_patterns:
            return 0.0

        # Simple intent detection based on patterns
        # In a real implementation, this would use NLP/ML models
        message_lower = message.lower()

        for pattern in intent_patterns:
            if isinstance(pattern, str):
                # Simple pattern matching - could be enhanced with ML
                pattern_keywords = pattern.lower().split()
                matches = sum(1 for keyword in pattern_keywords if keyword in message_lower)

                if matches > 0:
                    confidence = matches / len(pattern_keywords)
                    if confidence > 0.5:
                        return min(1.0, confidence)

        return 0.0

    async def test_workflow_trigger(
        self,
        workflow_id: str,
        tenant_id: str,
        message: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> TriggerCheckResponse:
        """Test if a specific workflow would be triggered by a message"""

        workflow = self.db.query(Workflow).filter(
            Workflow.id == workflow_id,
            Workflow.tenant_id == tenant_id
        ).first()

        if not workflow:
            return TriggerCheckResponse(triggered=False)

        confidence = self._calculate_trigger_confidence(workflow, message, user_context)
        triggered = confidence > 0.5

        return TriggerCheckResponse(
            triggered=triggered,
            workflow_id=workflow.id if triggered else None,
            workflow_name=workflow.name if triggered else None,
            confidence=confidence,
            trigger_type=workflow.trigger_type if triggered else None,
            metadata={
                "trigger_config": workflow.trigger_config,
                "test_mode": True
            } if triggered else None
        )

    @staticmethod
    def get_trigger_analytics(self, tenant_id: str, days: int = 30) -> Dict[str, Any]:
        """Get analytics about trigger performance"""
        # TODO: Implement trigger analytics
        # This would track:
        # - Most triggered workflows
        # - Trigger success rates
        # - Common trigger phrases
        # - User engagement after triggers

        return {
            "total_triggers": 0,
            "workflows_triggered": 0,
            "top_workflows": [],
            "trigger_success_rate": 0.0
        }