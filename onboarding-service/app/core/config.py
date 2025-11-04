from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings - Non-sensitive configuration only
    All sensitive values (API keys, secrets, URLs) must be loaded from environment variables
    """
    
    # API Configuration (non-sensitive)
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Onboarding Service"
    
    # Scraping Defaults (non-sensitive)
    MAX_PAGES_PER_SITE: int = 100
    SCRAPING_DELAY: float = 1.0

    # Scraping Strategy Configuration
    SCRAPING_STRATEGY: str = "auto"  # auto | requests_first | playwright_only | requests_only
    ENABLE_FALLBACK: bool = True  # Enable fallback to alternative scraper if primary fails
    PLAYWRIGHT_TIMEOUT: int = 30000  # Playwright timeout in milliseconds (30 seconds)
    REQUESTS_TIMEOUT: int = 10  # Requests timeout in seconds

    # Deprecated (kept for backward compatibility)
    USE_JAVASCRIPT_SCRAPING: bool = False
    
    # Password Policy (non-sensitive)
    PASSWORD_MIN_LENGTH: int = 8

    # Note: Billing configuration has been moved to the Billing Service

    # Database Pool Defaults (non-sensitive)
    POOL_SIZE: int = 10
    POOL_MAX_OVERFLOW: int = 20
    POOL_RECYCLE_SECONDS: int = 3600
    
    # AWS Region Default (non-sensitive)
    AWS_REGION: str = "us-east-1"
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()