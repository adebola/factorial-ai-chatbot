import re
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from ..models.workflow_model import Workflow, TriggerType
from ..schemas.workflow_schema import TriggerCheckResponse
from ..core.logging_config import get_logger, log_workflow_trigger
from .intent_embedding_service import IntentEmbeddingService

logger = get_logger("trigger_detector")


def _get_intent_patterns(workflow: Workflow) -> list:
    """
    Resolve intent_patterns for an intent workflow.

    Checks multiple locations in priority order because the WorkflowTrigger schema
    has both 'conditions' and 'intent_patterns' fields, and callers may use either:
      1. trigger_config.intent_patterns
      2. definition.trigger.intent_patterns
      3. trigger_config.conditions  (commonly used for intent phrases)
      4. definition.trigger.conditions
    """
    trigger_config = workflow.trigger_config or {}
    definition = workflow.definition or {}
    trigger_def = definition.get("trigger", {})

    # Check intent_patterns first (both locations), then fall back to conditions
    for source, key in [
        (trigger_config, "intent_patterns"),
        (trigger_def, "intent_patterns"),
        (trigger_config, "conditions"),
        (trigger_def, "conditions"),
    ]:
        patterns = source.get(key, []) or []
        if patterns:
            return patterns
    return []


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

        logger.info(f"Found {len(active_workflows)} active workflows for tenant {tenant_id}")
        logger.info(f"Checking message: '{message}' against workflows")

        # Backfill: generate missing intent_embeddings for workflows whose
        # trigger_config is incomplete (patterns only in definition, or
        # embeddings missing because OPENAI_API_KEY was unavailable at create time)
        for workflow in active_workflows:
            trigger_type_str = workflow.trigger_type.value if hasattr(workflow.trigger_type, 'value') else workflow.trigger_type
            if trigger_type_str == "intent":
                trigger_config = workflow.trigger_config or {}
                intent_patterns = _get_intent_patterns(workflow)
                intent_embeddings = trigger_config.get("intent_embeddings", [])
                if intent_patterns and not intent_embeddings:
                    try:
                        embedding_service = IntentEmbeddingService()
                        embeddings = embedding_service.generate_pattern_embeddings(intent_patterns)
                        # Sync intent_patterns + embeddings into trigger_config
                        trigger_config["intent_patterns"] = intent_patterns
                        trigger_config["intent_embeddings"] = embeddings
                        workflow.trigger_config = trigger_config
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(workflow, "trigger_config")
                        self.db.commit()
                        logger.info(f"Backfilled intent_patterns and embeddings for workflow {workflow.id}")
                    except Exception as e:
                        logger.warning(f"Failed to backfill intent embeddings for workflow {workflow.id}: {e}")

        if not active_workflows:
            log_workflow_trigger(
                tenant_id=tenant_id,
                trigger_type="none",
                message=message,
                triggered=False,
                reason="no_active_workflows"
            )
            return TriggerCheckResponse(triggered=False)

        # Pre-compute message embedding once if any workflow uses intent triggers
        message_embedding = None
        has_intent_workflows = any(
            (w.trigger_type.value if hasattr(w.trigger_type, 'value') else w.trigger_type) == "intent"
            for w in active_workflows
        )
        if has_intent_workflows:
            try:
                embedding_service = IntentEmbeddingService()
                message_embedding = embedding_service.embed_message(message)
            except Exception as e:
                logger.warning(f"Failed to embed message for intent matching, falling back to keyword: {e}")

        # Check each workflow for triggers
        best_match = None
        highest_confidence = 0.0

        for workflow in active_workflows:
            trigger_type_str = workflow.trigger_type.value if hasattr(workflow.trigger_type, 'value') else workflow.trigger_type
            tc = workflow.trigger_config or {}
            logger.info(
                f"Checking workflow {workflow.id} ('{workflow.name}'): trigger_type={trigger_type_str}, "
                f"trigger_config_keys={list(tc.keys())}, conditions={tc.get('conditions', [])}, "
                f"intent_patterns_raw={tc.get('intent_patterns', [])}, resolved_patterns={_get_intent_patterns(workflow)}"
            )
            confidence = self._calculate_trigger_confidence(workflow, message, user_context, message_embedding=message_embedding)
            logger.info(f"Workflow {workflow.id} confidence: {confidence}")

            if confidence > highest_confidence and confidence > 0.5:  # Minimum confidence threshold
                highest_confidence = confidence
                best_match = workflow

        if best_match:
            trigger_type_str = best_match.trigger_type.value if hasattr(best_match.trigger_type, 'value') else best_match.trigger_type
            log_workflow_trigger(
                tenant_id=tenant_id,
                trigger_type=trigger_type_str,
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
        user_context: Optional[Dict[str, Any]] = None,
        message_embedding: Optional[List[float]] = None
    ) -> float:
        """Calculate confidence score for workflow trigger (0.0 to 1.0)"""

        # Convert trigger_type to string for comparison (handles both enum and string types)
        trigger_type_str = workflow.trigger_type.value if hasattr(workflow.trigger_type, 'value') else str(workflow.trigger_type)

        if trigger_type_str == "message":
            return _check_message_trigger(workflow, message)
        elif trigger_type_str == "keyword":
            return self._check_keyword_trigger(workflow, message)
        elif trigger_type_str == "intent":
            return self._check_intent_trigger(workflow, message, user_context, message_embedding=message_embedding)
        else:
            return 0.0

    @staticmethod
    def _check_keyword_trigger(workflow: Workflow, message: str) -> float:
        """Check keyword-based triggers, search for the keyword in the message"""
        trigger_config = workflow.trigger_config or {}
        keywords = trigger_config.get("keywords", [])

        logger.info(f"[KEYWORD CHECK] Workflow {workflow.id}: keywords={keywords}")

        if not keywords:
            logger.info(f"[KEYWORD CHECK] No keywords configured")
            return 0.0

        message_lower = message.lower()
        matches = 0

        for keyword in keywords:
            if isinstance(keyword, str):
                # Exact word match (not just substring)
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                found = re.search(pattern, message_lower)
                logger.info(f"[KEYWORD CHECK] Testing keyword '{keyword}' with pattern '{pattern}' against '{message_lower}': match={bool(found)}")
                if found:
                    matches += 1

        if matches == 0:
            logger.info(f"[KEYWORD CHECK] No keyword matches found")
            return 0.0

        # Higher confidence for more keyword matches
        confidence = min(1.0, matches / len(keywords) * 1.2)
        logger.info(f"[KEYWORD CHECK] {matches}/{len(keywords)} keywords matched, confidence={confidence}")
        return confidence

    @staticmethod
    def _check_intent_trigger(
        workflow: Workflow,
        message: str,
        user_context: Optional[Dict[str, Any]] = None,
        message_embedding: Optional[List[float]] = None
    ) -> float:
        """
        Check intent-based triggers using embeddings when available,
        falling back to keyword matching otherwise.
        """
        trigger_config = workflow.trigger_config or {}
        intent_patterns = _get_intent_patterns(workflow)

        if not intent_patterns:
            logger.info(f"[INTENT] Workflow {workflow.id}: no intent_patterns in trigger_config or definition")
            return 0.0

        # Use embedding-based cosine similarity when both message embedding
        # and pre-computed pattern embeddings are available
        intent_embeddings = trigger_config.get("intent_embeddings", [])
        if message_embedding and intent_embeddings:
            best_similarity = 0.0
            best_pattern = None
            for entry in intent_embeddings:
                pattern_vec = entry.get("embedding")
                if not pattern_vec:
                    continue
                similarity = IntentEmbeddingService.cosine_similarity(message_embedding, pattern_vec)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_pattern = entry.get("text", "")

            # Map cosine similarity (typically 0.7-1.0 range for related text) to confidence
            # Threshold: similarity >= 0.82 → high confidence trigger
            if best_similarity >= 0.82:
                confidence = min(1.0, (best_similarity - 0.7) / 0.3)  # 0.7→0, 1.0→1.0
                logger.info(
                    f"[INTENT NLP] Workflow {workflow.id}: best match '{best_pattern}' "
                    f"similarity={best_similarity:.3f} confidence={confidence:.3f}"
                )
                return confidence

            logger.info(
                f"[INTENT NLP] Workflow {workflow.id}: no match above threshold, "
                f"best='{best_pattern}' similarity={best_similarity:.3f}"
            )
            return 0.0

        # Fallback: keyword-based matching (no embeddings stored)
        logger.info(f"[INTENT FALLBACK] Workflow {workflow.id}: no intent_embeddings stored, using keyword fallback")
        message_lower = message.lower()

        for pattern in intent_patterns:
            if isinstance(pattern, str):
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