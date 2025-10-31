"""
Configuration settings for Answer Quality Service.

IMPORTANT: Sensitive values (API keys, secrets, URLs) are loaded from environment variables only.
Never hardcode sensitive values in this file as it's checked into version control.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Service Configuration
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "answer-quality-service"
    API_V1_STR: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8005

    # Database (sensitive - must be in environment)
    DATABASE_URL: str

    # Redis (sensitive - must be in environment)
    REDIS_URL: str

    # RabbitMQ (sensitive - must be in environment)
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: str
    RABBITMQ_VHOST: str = "/"

    # RabbitMQ Queues
    QUEUE_CHAT_MESSAGES: str = "answer_quality.chat_messages"
    QUEUE_FEEDBACK_EVENTS: str = "answer_quality.feedback_events"

    # RabbitMQ Exchanges
    EXCHANGE_CHAT_EVENTS: str = "chat.events"
    EXCHANGE_QUALITY_EVENTS: str = "quality.events"

    # Chat Service Integration (sensitive - must be in environment)
    CHAT_SERVICE_URL: str
    CHAT_SERVICE_TIMEOUT: int = 10

    # Authorization Server (sensitive - must be in environment)
    AUTH_SERVER_URL: str

    # JWT Configuration
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str
    JWKS_URL: Optional[str] = None

    # Feature Flags
    ENABLE_BASIC_SENTIMENT: bool = True
    ENABLE_GAP_DETECTION: bool = True
    ENABLE_SESSION_TRACKING: bool = True

    # Quality Thresholds
    LOW_CONFIDENCE_THRESHOLD: float = 0.5
    GAP_DETECTION_THRESHOLD: int = 3
    SESSION_TIMEOUT_MINUTES: int = 30

    # Admin Dashboard
    ENABLE_ADMIN_DASHBOARD: bool = True

    # Scheduler & Background Jobs
    ENABLE_SCHEDULER: bool = True
    GAP_DETECTION_SCHEDULE: str = "0 2 * * *"  # Daily at 2 AM (cron format)
    GAP_DETECTION_LOOKBACK_DAYS: int = 7
    QUALITY_CHECK_SCHEDULE: str = "0 * * * *"  # Every hour (cron format)

    # Communications Service (for alert emails)
    COMMUNICATIONS_SERVICE_URL: str = "http://localhost:8003"
    ALERT_EMAIL_FROM: str = "alerts@factorialbot.com"

    # Alert Defaults
    DEFAULT_ALERT_THROTTLE_MINUTES: int = 1440  # 24 hours

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables


# Global settings instance
settings = Settings()
