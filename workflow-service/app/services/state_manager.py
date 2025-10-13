"""
State management for workflow execution.
Handles both Redis and database persistence for workflow states.
"""
import json
import redis
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..models.execution_model import WorkflowState, WorkflowExecution
from ..core.exceptions import WorkflowStateError
from ..core.logging_config import get_logger
from .redis_auth_cache import redis_token_cache  # Reuse Redis connection

logger = get_logger("state_manager")


class StateManager:
    """Manages workflow state persistence in Redis and database"""

    def __init__(self, db: Session):
        self.db = db
        # Reuse the existing Redis connection from auth cache
        self.redis_client = redis_token_cache.redis_client
        self.state_prefix = "workflow:state:"
        self.default_ttl = 3600  # 1 hour default TTL

    async def save_state(
        self,
        session_id: str,
        execution_id: str,
        workflow_id: str,
        tenant_id: str,
        current_step_id: str,
        variables: Dict[str, Any],
        step_context: Optional[Dict[str, Any]] = None,
        waiting_for_input: Optional[str] = None,
        last_user_message: Optional[str] = None,
        last_bot_message: Optional[str] = None,
        ttl_hours: int = 1
    ) -> bool:
        """
        Save workflow state to both Redis and database.

        Args:
            session_id: Chat session ID
            execution_id: Workflow execution ID
            workflow_id: Workflow ID
            tenant_id: Tenant ID
            current_step_id: Current step in workflow
            variables: Workflow variables
            step_context: Step-specific context
            waiting_for_input: Type of input expected from user
            last_user_message: Last message from user
            last_bot_message: Last message from bot
            ttl_hours: Hours until state expires

        Returns:
            True if saved successfully
        """
        try:
            expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

            # Prepare state data
            now = datetime.utcnow()
            state_data = {
                "session_id": session_id,
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "tenant_id": tenant_id,
                "current_step_id": current_step_id,
                "variables": variables or {},
                "step_context": step_context or {},
                "waiting_for_input": waiting_for_input,
                "last_user_message": last_user_message,
                "last_bot_message": last_bot_message,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "updated_at": now.isoformat()
            }

            # Save to Redis for fast access
            redis_key = f"{self.state_prefix}{session_id}"
            ttl_seconds = ttl_hours * 3600

            await self._save_to_redis(redis_key, state_data, ttl_seconds)

            # Save to database for persistence
            await self._save_to_database(state_data, expires_at)

            logger.debug(f"State saved for session {session_id}, step {current_step_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save state for session {session_id}: {e}")
            return False

    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow state for a session.
        Tries Redis first, falls back to database.

        Args:
            session_id: Chat session ID

        Returns:
            State data or None if not found
        """
        try:
            # Try Redis first
            redis_key = f"{self.state_prefix}{session_id}"
            state_data = await self._get_from_redis(redis_key)

            if state_data:
                # Check if expired
                expires_at = datetime.fromisoformat(state_data.get("expires_at", ""))
                if datetime.utcnow() > expires_at:
                    await self.delete_state(session_id)
                    return None

                logger.debug(f"State retrieved from Redis for session {session_id}")
                return state_data

            # Fall back to database
            state_data = await self._get_from_database(session_id)
            if state_data:
                # Restore to Redis
                expires_at = datetime.fromisoformat(state_data["expires_at"])
                remaining_seconds = int((expires_at - datetime.utcnow()).total_seconds())
                if remaining_seconds > 0:
                    await self._save_to_redis(redis_key, state_data, remaining_seconds)
                    logger.debug(f"State retrieved from database and cached for session {session_id}")
                    return state_data
                else:
                    # Expired, clean up
                    await self.delete_state(session_id)
                    return None

            return None

        except Exception as e:
            logger.error(f"Failed to get state for session {session_id}: {e}")
            return None

    async def update_variables(
        self,
        session_id: str,
        variables: Dict[str, Any],
        merge: bool = True
    ) -> bool:
        """
        Update workflow variables for a session.

        Args:
            session_id: Chat session ID
            variables: New variables to set
            merge: Whether to merge with existing variables

        Returns:
            True if updated successfully
        """
        try:
            current_state = await self.get_state(session_id)
            if not current_state:
                raise WorkflowStateError(f"No state found for session {session_id}")

            if merge:
                current_variables = current_state.get("variables", {})
                current_variables.update(variables)
                updated_variables = current_variables
            else:
                updated_variables = variables

            # Update the state
            await self.save_state(
                session_id=session_id,
                execution_id=current_state["execution_id"],
                workflow_id=current_state["workflow_id"],
                tenant_id=current_state["tenant_id"],
                current_step_id=current_state["current_step_id"],
                variables=updated_variables,
                step_context=current_state.get("step_context"),
                waiting_for_input=current_state.get("waiting_for_input"),
                last_user_message=current_state.get("last_user_message"),
                last_bot_message=current_state.get("last_bot_message")
            )

            logger.debug(f"Variables updated for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update variables for session {session_id}: {e}")
            return False

    async def advance_step(
        self,
        session_id: str,
        new_step_id: str,
        step_context: Optional[Dict[str, Any]] = None,
        waiting_for_input: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Advance workflow to the next step.

        Args:
            session_id: Chat session ID
            new_step_id: ID of the next step
            step_context: Context for the new step
            waiting_for_input: Type of input expected
            variables: Updated variables to save (if None, will use current state variables)

        Returns:
            True if advanced successfully
        """
        try:
            current_state = await self.get_state(session_id)
            if not current_state:
                raise WorkflowStateError(f"No state found for session {session_id}")

            # Use provided variables or fall back to current state variables
            variables_to_save = variables if variables is not None else current_state.get("variables", {})

            # Update the state
            await self.save_state(
                session_id=session_id,
                execution_id=current_state["execution_id"],
                workflow_id=current_state["workflow_id"],
                tenant_id=current_state["tenant_id"],
                current_step_id=new_step_id,
                variables=variables_to_save,
                step_context=step_context or {},
                waiting_for_input=waiting_for_input,
                last_user_message=current_state.get("last_user_message"),
                last_bot_message=current_state.get("last_bot_message")
            )

            logger.debug(f"Advanced to step {new_step_id} for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to advance step for session {session_id}: {e}")
            return False

    async def mark_completed(self, session_id: str) -> bool:
        """
        Mark workflow state as completed instead of deleting it.
        The state will expire naturally based on TTL.

        Args:
            session_id: Chat session ID

        Returns:
            True if marked successfully
        """
        try:
            current_state = await self.get_state(session_id)
            if not current_state:
                logger.warning(f"No state found to mark as completed for session {session_id}")
                return False

            # Add completion flag to variables
            variables = current_state.get("variables", {})
            variables["__workflow_completed"] = True

            # Update the state with completion flag
            await self.save_state(
                session_id=session_id,
                execution_id=current_state["execution_id"],
                workflow_id=current_state["workflow_id"],
                tenant_id=current_state["tenant_id"],
                current_step_id=current_state["current_step_id"],
                variables=variables,
                step_context=current_state.get("step_context"),
                waiting_for_input=None,  # Clear waiting state
                last_user_message=current_state.get("last_user_message"),
                last_bot_message=current_state.get("last_bot_message")
            )

            logger.debug(f"State marked as completed for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark state as completed for session {session_id}: {e}")
            return False

    async def delete_state(self, session_id: str) -> bool:
        """
        Delete workflow state for a session.

        Args:
            session_id: Chat session ID

        Returns:
            True if deleted successfully
        """
        try:
            # Delete from Redis
            redis_key = f"{self.state_prefix}{session_id}"
            self.redis_client.delete(redis_key)

            # Delete from database
            self.db.query(WorkflowState).filter(
                WorkflowState.session_id == session_id
            ).delete()
            self.db.commit()

            logger.debug(f"State deleted for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete state for session {session_id}: {e}")
            self.db.rollback()
            return False

    async def cleanup_expired_states(self) -> int:
        """
        Clean up expired workflow states from database.

        Returns:
            Number of states cleaned up
        """
        try:
            count = self.db.query(WorkflowState).filter(
                WorkflowState.expires_at < datetime.utcnow()
            ).count()

            # Delete expired states
            self.db.query(WorkflowState).filter(
                WorkflowState.expires_at < datetime.utcnow()
            ).delete()
            self.db.commit()

            logger.info(f"Cleaned up {count} expired workflow states from database")
            return count

        except Exception as e:
            logger.error(f"Failed to cleanup expired states: {e}")
            self.db.rollback()
            return 0

    async def cleanup_orphaned_redis_states(self) -> int:
        """
        Clean up orphaned Redis workflow states that have no corresponding database record.
        This can happen when Redis TTL expires but workflow wasn't properly cleaned up,
        or when database records are deleted but Redis keys remain.

        Returns:
            Number of orphaned Redis states cleaned up
        """
        try:
            pattern = f"{self.state_prefix}*"
            # Get all workflow state keys from Redis
            redis_keys = self.redis_client.keys(pattern)

            if not redis_keys:
                return 0

            orphaned = 0
            for key in redis_keys:
                # Extract session_id from Redis key
                session_id = key.replace(self.state_prefix, "")

                # Check if database state exists
                state = self.db.query(WorkflowState).filter(
                    WorkflowState.session_id == session_id
                ).first()

                if not state:
                    # No database state found, this is an orphaned Redis key
                    self.redis_client.delete(key)
                    orphaned += 1
                    logger.debug(f"Removed orphaned Redis state: {session_id}")

            if orphaned > 0:
                logger.info(f"Cleaned up {orphaned} orphaned Redis workflow states")

            return orphaned

        except Exception as e:
            logger.error(f"Failed to cleanup orphaned Redis states: {e}")
            return 0

    async def get_active_sessions_for_tenant(self, tenant_id: str) -> list:
        """
        Get all active workflow sessions for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of active session IDs
        """
        try:
            states = self.db.query(WorkflowState).filter(
                WorkflowState.tenant_id == tenant_id,
                WorkflowState.expires_at > datetime.utcnow()
            ).all()

            return [state.session_id for state in states]

        except Exception as e:
            logger.error(f"Failed to get active sessions for tenant {tenant_id}: {e}")
            return []

    async def _save_to_redis(
        self,
        key: str,
        data: Dict[str, Any],
        ttl_seconds: int
    ) -> None:
        """Save state data to Redis"""
        try:
            serialized_data = json.dumps(data)
            self.redis_client.setex(key, ttl_seconds, serialized_data)
        except Exception as e:
            logger.error(f"Failed to save to Redis: {e}")
            raise

    async def _get_from_redis(self, key: str) -> Optional[Dict[str, Any]]:
        """Get state data from Redis"""
        try:
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get from Redis: {e}")
            return None

    async def _save_to_database(
        self,
        state_data: Dict[str, Any],
        expires_at: datetime
    ) -> None:
        """Save state data to database"""
        try:
            # Check if state already exists
            existing_state = self.db.query(WorkflowState).filter(
                WorkflowState.session_id == state_data["session_id"]
            ).first()

            if existing_state:
                # Update existing state
                existing_state.execution_id = state_data["execution_id"]
                existing_state.workflow_id = state_data["workflow_id"]
                existing_state.current_step_id = state_data["current_step_id"]
                existing_state.step_context = state_data.get("step_context", {})
                existing_state.variables = state_data.get("variables", {})
                existing_state.waiting_for_input = state_data.get("waiting_for_input")
                existing_state.last_user_message = state_data.get("last_user_message")
                existing_state.last_bot_message = state_data.get("last_bot_message")
                existing_state.expires_at = expires_at
                existing_state.updated_at = datetime.utcnow()
            else:
                # Create new state
                new_state = WorkflowState(
                    session_id=state_data["session_id"],
                    execution_id=state_data["execution_id"],
                    workflow_id=state_data["workflow_id"],
                    tenant_id=state_data["tenant_id"],
                    current_step_id=state_data["current_step_id"],
                    step_context=state_data.get("step_context", {}),
                    variables=state_data.get("variables", {}),
                    waiting_for_input=state_data.get("waiting_for_input"),
                    last_user_message=state_data.get("last_user_message"),
                    last_bot_message=state_data.get("last_bot_message"),
                    expires_at=expires_at
                )
                self.db.add(new_state)

            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to save to database: {e}")
            self.db.rollback()
            raise

    async def _get_from_database(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get state data from database"""
        try:
            state = self.db.query(WorkflowState).filter(
                WorkflowState.session_id == session_id
            ).first()

            if not state:
                return None

            return {
                "session_id": state.session_id,
                "execution_id": state.execution_id,
                "workflow_id": state.workflow_id,
                "tenant_id": state.tenant_id,
                "current_step_id": state.current_step_id,
                "variables": state.variables or {},
                "step_context": state.step_context or {},
                "waiting_for_input": state.waiting_for_input,
                "last_user_message": state.last_user_message,
                "last_bot_message": state.last_bot_message,
                "created_at": state.created_at.isoformat() if state.created_at else None,
                "expires_at": state.expires_at.isoformat() if state.expires_at else None,
                "updated_at": state.updated_at.isoformat() if state.updated_at else None
            }

        except Exception as e:
            logger.error(f"Failed to get from database: {e}")
            return None