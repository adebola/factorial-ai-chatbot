"""Fire-and-forget token usage recording service."""
import uuid
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..core.logging_config import get_logger
from ..models.tenant import TokenUsage
from .token_cost import estimate_cost

logger = get_logger("token_usage")


class TokenUsageService:
    """Records token usage to the database. Uses its own session for safety."""

    def record_usage(
        self,
        tenant_id: str,
        model: str,
        usage_type: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        source_id: str = None,
    ):
        """Record a token usage entry. Failures only log a warning."""
        try:
            cost = estimate_cost(model, prompt_tokens, completion_tokens)
            db: Session = SessionLocal()
            try:
                record = TokenUsage(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    source_id=source_id,
                    model=model,
                    usage_type=usage_type,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens or (prompt_tokens + completion_tokens),
                    estimated_cost_usd=cost,
                )
                db.add(record)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to record token usage: {e}")


token_usage_service = TokenUsageService()
