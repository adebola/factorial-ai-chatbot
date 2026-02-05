"""
Audit Service for tracking administrative actions.

This service provides comprehensive audit logging for all admin operations
across the billing system. It tracks who did what, when, and why.
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ..core.database import Base
from .dependencies import TokenClaims

logger = logging.getLogger(__name__)


class AdminAction(Base):
    """
    Model for tracking administrative actions.

    Every admin operation (manual payment, subscription override, etc.)
    is logged here for compliance and audit purposes.
    """
    __tablename__ = "admin_actions"

    # Primary key
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # Admin user information
    admin_user_id = Column(String(36), nullable=False, index=True)
    admin_email = Column(String(255), nullable=False)
    admin_full_name = Column(String(255), nullable=True)

    # Action details
    action_type = Column(String(50), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(String(36), nullable=False, index=True)
    target_tenant_id = Column(String(36), nullable=True, index=True)

    # State tracking
    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)

    # Reason and context
    reason = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Additional metadata
    action_metadata = Column(JSONB, nullable=True, default={})

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Indexes defined at table level
    __table_args__ = (
        Index('ix_admin_actions_tenant_action_type', 'target_tenant_id', 'action_type', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "admin_user_id": self.admin_user_id,
            "admin_email": self.admin_email,
            "admin_full_name": self.admin_full_name,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_tenant_id": self.target_tenant_id,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "reason": self.reason,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "action_metadata": self.action_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditService:
    """
    Service for logging administrative actions.

    This service provides a centralized way to log all admin operations
    with consistent formatting and metadata.
    """

    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        admin_claims: TokenClaims,
        action_type: str,
        target_type: str,
        target_id: str,
        target_tenant_id: Optional[str] = None,
        before_state: Optional[Dict] = None,
        after_state: Optional[Dict] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> AdminAction:
        """
        Log an administrative action.

        Args:
            admin_claims: TokenClaims of the admin user performing the action
            action_type: Type of action (e.g., 'manual_payment', 'subscription_override')
            target_type: Type of resource being modified (e.g., 'payment', 'subscription')
            target_id: ID of the resource being modified
            target_tenant_id: Tenant ID affected by this action (optional)
            before_state: State of the resource before the action
            after_state: State of the resource after the action
            reason: Human-readable reason for the action
            ip_address: IP address of the admin user
            user_agent: User agent string from the request
            metadata: Additional metadata about the action

        Returns:
            AdminAction: The created audit log entry
        """
        try:
            action = AdminAction(
                id=str(uuid.uuid4()),
                admin_user_id=admin_claims.user_id,
                admin_email=admin_claims.email or "unknown",
                admin_full_name=admin_claims.full_name,
                action_type=action_type,
                target_type=target_type,
                target_id=target_id,
                target_tenant_id=target_tenant_id,
                before_state=before_state,
                after_state=after_state,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                action_metadata=metadata or {}
            )

            self.db.add(action)
            self.db.commit()
            self.db.refresh(action)

            logger.info(
                f"Admin action logged: {action_type} on {target_type}:{target_id} by {admin_claims.email}",
                extra={
                    "action_id": action.id,
                    "admin_user_id": admin_claims.user_id,
                    "action_type": action_type,
                    "target_type": target_type,
                    "target_id": target_id,
                    "target_tenant_id": target_tenant_id
                }
            )

            return action

        except Exception as e:
            logger.error(
                f"Failed to log admin action: {e}",
                extra={
                    "admin_user_id": admin_claims.user_id,
                    "action_type": action_type,
                    "target_type": target_type,
                    "target_id": target_id
                }
            )
            self.db.rollback()
            raise

    def get_actions_by_admin(
        self,
        admin_user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> list[AdminAction]:
        """Get all actions performed by a specific admin user"""
        return (
            self.db.query(AdminAction)
            .filter(AdminAction.admin_user_id == admin_user_id)
            .order_by(AdminAction.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_actions_by_tenant(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> list[AdminAction]:
        """Get all admin actions affecting a specific tenant"""
        return (
            self.db.query(AdminAction)
            .filter(AdminAction.target_tenant_id == tenant_id)
            .order_by(AdminAction.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_actions_by_type(
        self,
        action_type: str,
        limit: int = 50,
        offset: int = 0
    ) -> list[AdminAction]:
        """Get all actions of a specific type"""
        return (
            self.db.query(AdminAction)
            .filter(AdminAction.action_type == action_type)
            .order_by(AdminAction.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_actions_by_target(
        self,
        target_type: str,
        target_id: str
    ) -> list[AdminAction]:
        """Get all admin actions on a specific resource"""
        return (
            self.db.query(AdminAction)
            .filter(
                AdminAction.target_type == target_type,
                AdminAction.target_id == target_id
            )
            .order_by(AdminAction.created_at.desc())
            .all()
        )
