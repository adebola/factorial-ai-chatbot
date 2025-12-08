from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Billing Service Configuration - Non-sensitive settings only
    All sensitive values (API keys, secrets, URLs) must be loaded from environment variables
    """

    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Billing Service"

    # Billing Defaults
    DEFAULT_CURRENCY: str = "NGN"
    SUBSCRIPTION_GRACE_PERIOD_DAYS: int = 3
    TRIAL_PERIOD_DAYS: int = 14

    # Database Pool Settings
    POOL_SIZE: int = 10
    POOL_MAX_OVERFLOW: int = 20
    POOL_RECYCLE_SECONDS: int = 300  # Recycle connections every 5 minutes (was 3600/1 hour)
    POOL_TIMEOUT: int = 30  # Wait max 30 seconds for connection from pool
    CONNECT_TIMEOUT: int = 10  # Connection timeout in seconds

    # JWT Token Settings
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
