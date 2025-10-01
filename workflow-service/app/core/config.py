from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Basic service configuration
    PROJECT_NAME: str = "Workflow Service"
    API_V1_STR: str = "/api/v1"
    SERVICE_NAME: str = "workflow-service"

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # External service URLs (no sensitive data here)
    CHAT_SERVICE_URL: str = "http://localhost:8000"
    ONBOARDING_SERVICE_URL: str = "http://localhost:8001"
    COMMUNICATIONS_SERVICE_URL: str = "http://localhost:8003"
    AUTHORIZATION_SERVICE_URL: str = "http://localhost:9000"

    # JWT settings (issuer only, secret comes from environment)
    JWT_ISSUER: str = "http://localhost:9000/auth"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()