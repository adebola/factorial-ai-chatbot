"""
Answer Feedback Model

Stores user feedback (👍/👎) on AI responses.
"""

from sqlalchemy import Column, String, Text, DateTime, func
from app.core.database import Base


class AnswerFeedback(Base):
    """
    User feedback on AI responses.

    Feedback can be:
    - 'helpful': User found the answer helpful (👍)
    - 'not_helpful': User found the answer not helpful (👎)
    """

    __tablename__ = "answer_feedback"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=False, index=True)  # References chat_messages.id

    feedback_type = Column(String(20), nullable=False)  # 'helpful' or 'not_helpful'
    feedback_comment = Column(Text, nullable=True)  # Optional user comment

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<AnswerFeedback(id={self.id}, message_id={self.message_id}, feedback_type={self.feedback_type})>"
