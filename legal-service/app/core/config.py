from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Non-sensitive configuration only. Sensitive values come from environment."""
    PROJECT_NAME: str = "Legal Service"
    API_V1_STR: str = "/api/v1"
    SERVICE_NAME: str = "legal-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # External service URLs (non-sensitive, overridden in Docker/K8s)
    CHAT_SERVICE_URL: str = "http://localhost:8000"
    ONBOARDING_SERVICE_URL: str = "http://localhost:8001"
    AUTHORIZATION_SERVER_URL: str = "http://localhost:9002/auth"
    BILLING_SERVICE_URL: str = "http://localhost:8004"

    # JWT configuration
    JWT_ISSUER: str = "http://localhost:9002/auth"

    # Document processing
    CHUNK_SIZE: int = 1500
    CHUNK_OVERLAP: int = 300
    EMBEDDING_MODEL: str = "text-embedding-ada-002"
    EMBEDDING_DIMENSIONS: int = 1536

    # MinIO storage prefix
    MINIO_LEGAL_PREFIX: str = "legal"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
