from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Non-sensitive configuration only. Sensitive values come from environment."""
    PROJECT_NAME: str = "Observability Service"
    API_V1_STR: str = "/api/v1"
    SERVICE_NAME: str = "observability-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # External service URLs (non-sensitive, overridden in Docker/K8s)
    CHAT_SERVICE_URL: str = "http://localhost:8000"
    ONBOARDING_SERVICE_URL: str = "http://localhost:8001"
    AUTHORIZATION_SERVER_URL: str = "http://localhost:9002/auth"
    BILLING_SERVICE_URL: str = "http://localhost:8004"

    # JWT configuration
    JWT_ISSUER: str = "http://localhost:9002/auth"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
