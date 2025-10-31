"""
Job Execution Log Model

Records execution history of scheduled background jobs.
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from app.core.database import Base


class JobExecutionLog(Base):
    """
    Execution log for scheduled background jobs.

    Tracks when jobs run, how long they take, and their success/failure status.
    """

    __tablename__ = "job_execution_logs"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=True, index=True)  # Nullable for system-wide jobs

    # Job Information
    job_name = Column(String(100), nullable=False, index=True)
    job_type = Column(String(50), nullable=False)  # gap_detection, quality_check, weekly_report, etc.

    # Execution Details
    status = Column(String(20), nullable=False)  # success, failed, partial
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Execution time in milliseconds

    # Results
    result_summary = Column(JSON, nullable=True)  # {gaps_detected: 5, messages_processed: 100, etc.}
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)  # Stack trace, context, etc.

    # Metadata
    triggered_by = Column(String(50), default="scheduler", nullable=False)  # scheduler, manual, api
    triggered_by_user_id = Column(String(36), nullable=True)  # If manually triggered

    def __repr__(self):
        return f"<JobExecutionLog(id={self.id}, job={self.job_name}, status={self.status}, duration={self.duration_ms}ms)>"
