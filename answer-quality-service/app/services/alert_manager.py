"""
Alert Manager Service

Evaluates alert rules and triggers notifications when conditions are met.
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.models.alert_rule import AlertRule
from app.models.alert_history import AlertHistory
from app.models.quality_metrics import RAGQualityMetrics
from app.models.feedback import AnswerFeedback
from app.models.knowledge_gap import KnowledgeGap
from app.services.notification_client import notification_client
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AlertManager:
    """
    Manages alert rule evaluation and notification delivery.
    """

    def __init__(self, db: Session):
        self.db = db

    async def check_all_rules(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check all enabled alert rules for one or all tenants.

        Args:
            tenant_id: Specific tenant ID, or None to check all tenants

        Returns:
            Summary of triggered alerts
        """
        # Get enabled rules
        query = self.db.query(AlertRule).filter(AlertRule.enabled == True)

        if tenant_id:
            query = query.filter(AlertRule.tenant_id == tenant_id)

        rules = query.all()

        logger.info(
            "Checking alert rules",
            tenant_id=tenant_id or "all",
            rule_count=len(rules)
        )

        triggered_count = 0
        results = []

        for rule in rules:
            try:
                # Check if rule should be throttled
                if self._is_throttled(rule):
                    logger.debug(
                        "Alert rule throttled",
                        rule_id=rule.id,
                        rule_name=rule.name,
                        tenant_id=rule.tenant_id
                    )
                    continue

                # Evaluate the rule
                triggered, alert_data = await self._evaluate_rule(rule)

                if triggered:
                    # Trigger alert and send notifications
                    await self._trigger_alert(rule, alert_data)
                    triggered_count += 1
                    results.append({
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "tenant_id": rule.tenant_id,
                        "triggered": True
                    })

            except Exception as e:
                logger.error(
                    f"Error evaluating alert rule: {e}",
                    rule_id=rule.id,
                    rule_name=rule.name,
                    tenant_id=rule.tenant_id,
                    exc_info=True
                )
                results.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "tenant_id": rule.tenant_id,
                    "triggered": False,
                    "error": str(e)
                })

        logger.info(
            "Alert rule checking completed",
            tenant_id=tenant_id or "all",
            total_rules=len(rules),
            triggered_count=triggered_count
        )

        return {
            "total_rules_checked": len(rules),
            "alerts_triggered": triggered_count,
            "results": results
        }

    async def _evaluate_rule(self, rule: AlertRule) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Evaluate a single alert rule.

        Returns:
            Tuple of (triggered: bool, alert_data: Dict)
        """
        if rule.rule_type == "quality_drop":
            return await self._check_quality_drop(rule)
        elif rule.rule_type == "new_gaps":
            return await self._check_new_gaps(rule)
        elif rule.rule_type == "high_negative_feedback":
            return await self._check_high_negative_feedback(rule)
        elif rule.rule_type == "session_degradation":
            return await self._check_session_degradation(rule)
        else:
            logger.warning(
                f"Unknown rule type: {rule.rule_type}",
                rule_id=rule.id,
                tenant_id=rule.tenant_id
            )
            return False, None

    async def _check_quality_drop(self, rule: AlertRule) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check if average confidence has dropped below threshold."""

        cutoff_time = datetime.now() - timedelta(hours=rule.check_interval_hours)

        # Get average confidence in time period
        result = self.db.query(
            func.avg(RAGQualityMetrics.answer_confidence).label('avg_confidence'),
            func.count(RAGQualityMetrics.id).label('sample_size')
        ).filter(
            and_(
                RAGQualityMetrics.tenant_id == rule.tenant_id,
                RAGQualityMetrics.created_at >= cutoff_time,
                RAGQualityMetrics.answer_confidence.isnot(None)
            )
        ).first()

        avg_confidence = result.avg_confidence
        sample_size = result.sample_size

        # Check if we have enough samples
        if not avg_confidence or sample_size < rule.min_sample_size:
            return False, None

        # Check if threshold breached
        if avg_confidence < rule.threshold_value:
            alert_data = {
                "rule_type": "quality_drop",
                "message": f"Average answer confidence ({avg_confidence:.3f}) has dropped below threshold ({rule.threshold_value})",
                "current_value": round(avg_confidence, 3),
                "threshold": rule.threshold_value,
                "sample_size": sample_size,
                "time_period": f"Last {rule.check_interval_hours} hours"
            }
            return True, alert_data

        return False, None

    async def _check_new_gaps(self, rule: AlertRule) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check if new knowledge gaps have been detected."""

        cutoff_time = datetime.now() - timedelta(hours=rule.check_interval_hours)

        # Count new gaps detected in time period
        new_gaps_count = self.db.query(func.count(KnowledgeGap.id)).filter(
            and_(
                KnowledgeGap.tenant_id == rule.tenant_id,
                KnowledgeGap.first_detected_at >= cutoff_time,
                KnowledgeGap.status == "detected"
            )
        ).scalar()

        # Check if threshold breached (threshold = minimum gap count to trigger)
        if new_gaps_count >= rule.threshold_value:
            # Get gap examples
            gaps = self.db.query(KnowledgeGap).filter(
                and_(
                    KnowledgeGap.tenant_id == rule.tenant_id,
                    KnowledgeGap.first_detected_at >= cutoff_time,
                    KnowledgeGap.status == "detected"
                )
            ).order_by(desc(KnowledgeGap.occurrence_count)).limit(5).all()

            gap_examples = [
                {
                    "pattern": gap.question_pattern[:100],
                    "occurrences": gap.occurrence_count
                }
                for gap in gaps
            ]

            alert_data = {
                "rule_type": "new_gaps",
                "message": f"{new_gaps_count} new knowledge gaps detected in the last {rule.check_interval_hours} hours",
                "current_value": new_gaps_count,
                "threshold": rule.threshold_value,
                "time_period": f"Last {rule.check_interval_hours} hours",
                "gap_examples": gap_examples
            }
            return True, alert_data

        return False, None

    async def _check_high_negative_feedback(self, rule: AlertRule) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check if negative feedback rate is too high."""

        cutoff_time = datetime.now() - timedelta(hours=rule.check_interval_hours)

        # Count feedback by type
        feedback_stats = self.db.query(
            AnswerFeedback.feedback_type,
            func.count(AnswerFeedback.id).label('count')
        ).filter(
            and_(
                AnswerFeedback.tenant_id == rule.tenant_id,
                AnswerFeedback.created_at >= cutoff_time
            )
        ).group_by(AnswerFeedback.feedback_type).all()

        feedback_summary = {"helpful": 0, "not_helpful": 0}
        for feedback_type, count in feedback_stats:
            feedback_summary[feedback_type] = count

        total_feedback = sum(feedback_summary.values())

        # Check minimum sample size
        if total_feedback < rule.min_sample_size:
            return False, None

        # Calculate negative feedback rate
        negative_rate = feedback_summary["not_helpful"] / total_feedback if total_feedback > 0 else 0

        # Check if threshold breached
        if negative_rate > rule.threshold_value:
            alert_data = {
                "rule_type": "high_negative_feedback",
                "message": f"Negative feedback rate ({negative_rate:.1%}) exceeds threshold ({rule.threshold_value:.1%})",
                "current_value": round(negative_rate, 3),
                "threshold": rule.threshold_value,
                "sample_size": total_feedback,
                "helpful_count": feedback_summary["helpful"],
                "not_helpful_count": feedback_summary["not_helpful"],
                "time_period": f"Last {rule.check_interval_hours} hours"
            }
            return True, alert_data

        return False, None

    async def _check_session_degradation(self, rule: AlertRule) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Check for significant session quality degradation."""

        # This is a simplified check - could be enhanced with more sophisticated logic
        cutoff_time = datetime.now() - timedelta(hours=rule.check_interval_hours)

        # Get sessions with low quality in time period
        low_quality_sessions = self.db.query(func.count(RAGQualityMetrics.session_id.distinct())).filter(
            and_(
                RAGQualityMetrics.tenant_id == rule.tenant_id,
                RAGQualityMetrics.created_at >= cutoff_time,
                RAGQualityMetrics.answer_confidence < 0.4  # Very low confidence
            )
        ).scalar()

        # Check if threshold breached
        if low_quality_sessions >= rule.threshold_value:
            alert_data = {
                "rule_type": "session_degradation",
                "message": f"{low_quality_sessions} sessions with poor quality detected",
                "current_value": low_quality_sessions,
                "threshold": rule.threshold_value,
                "time_period": f"Last {rule.check_interval_hours} hours"
            }
            return True, alert_data

        return False, None

    async def _trigger_alert(self, rule: AlertRule, alert_data: Dict[str, Any]):
        """
        Trigger an alert: create history record and send notifications.
        """
        # Enhance alert data with rule information
        alert_data.update({
            "rule_name": rule.name,
            "rule_id": rule.id,
            "severity": self._determine_severity(rule, alert_data),
            "triggered_at": datetime.now().isoformat()
        })

        # Create alert history record
        alert_history = AlertHistory(
            id=str(uuid.uuid4()),
            tenant_id=rule.tenant_id,
            rule_id=rule.id,
            rule_name=rule.name,
            rule_type=rule.rule_type,
            severity=alert_data["severity"],
            alert_message=alert_data["message"],
            alert_data=alert_data,
            notification_sent=False
        )

        self.db.add(alert_history)
        self.db.flush()

        # Send notifications
        try:
            notification_results = await notification_client.send_notification(
                tenant_id=rule.tenant_id,
                alert_data=alert_data,
                channels=rule.notification_channels,
                recipients=rule.notification_recipients
            )

            # Update alert history with notification results
            alert_history.notification_sent = any(
                result.get("success", False) for result in notification_results.values()
            )
            alert_history.notification_channels_used = list(notification_results.keys())
            alert_history.notification_response = notification_results
            alert_history.processed_at = datetime.now()

            # Update rule's last triggered timestamp
            rule.last_triggered_at = datetime.now()

            self.db.commit()

            logger.info(
                "Alert triggered and notifications sent",
                rule_id=rule.id,
                rule_name=rule.name,
                tenant_id=rule.tenant_id,
                alert_id=alert_history.id,
                notification_results=notification_results
            )

        except Exception as e:
            logger.error(
                f"Failed to send alert notifications: {e}",
                rule_id=rule.id,
                tenant_id=rule.tenant_id,
                exc_info=True
            )

            alert_history.notification_sent = False
            alert_history.notification_error = str(e)
            alert_history.processed_at = datetime.now()
            self.db.commit()

    def _is_throttled(self, rule: AlertRule) -> bool:
        """Check if alert rule is currently throttled."""

        if not rule.last_triggered_at:
            return False

        # Calculate time since last trigger
        time_since_trigger = datetime.now() - rule.last_triggered_at
        throttle_period = timedelta(minutes=rule.throttle_minutes)

        return time_since_trigger < throttle_period

    def _determine_severity(self, rule: AlertRule, alert_data: Dict[str, Any]) -> str:
        """
        Determine alert severity based on rule and data.

        Returns: "info", "warning", or "critical"
        """
        current_value = alert_data.get("current_value", 0)
        threshold = alert_data.get("threshold", 0)

        # Calculate how far we've exceeded the threshold
        if rule.rule_type in ["quality_drop", "high_negative_feedback"]:
            # Lower is worse
            if threshold == 0:
                deviation_pct = 0
            else:
                deviation_pct = abs((threshold - current_value) / threshold)
        else:
            # Higher is worse
            if threshold == 0:
                deviation_pct = 1.0 if current_value > 0 else 0
            else:
                deviation_pct = (current_value - threshold) / threshold

        # Severity thresholds
        if deviation_pct > 0.5:  # >50% beyond threshold
            return "critical"
        elif deviation_pct > 0.2:  # 20-50% beyond threshold
            return "warning"
        else:
            return "info"
