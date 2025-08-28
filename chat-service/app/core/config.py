from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings - Non-sensitive configuration only
    All sensitive values (API keys, secrets, URLs) must be loaded from environment variables
    """
    
    # API Configuration (non-sensitive)
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Chat Service"
    
    # JWT Algorithm Default (non-sensitive)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()