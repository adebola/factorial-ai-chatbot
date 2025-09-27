from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings - Non-sensitive configuration only
    All sensitive values (API keys, secrets, URLs) must be loaded from environment variables
    """

    # API Configuration (non-sensitive)
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Communications Service"

    # Message limits (non-sensitive defaults)
    MAX_ATTACHMENT_SIZE_MB: int = 25  # SendGrid limit
    MAX_ATTACHMENTS_PER_EMAIL: int = 10
    MAX_EMAIL_RECIPIENTS: int = 1000
    MAX_SMS_LENGTH: int = 1600  # SMS standard limit

    # Rate limiting defaults (non-sensitive)
    DEFAULT_DAILY_EMAIL_LIMIT: int = 1000
    DEFAULT_DAILY_SMS_LIMIT: int = 100

    # Retry configuration (non-sensitive)
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: int = 60

    # Template defaults (non-sensitive)
    DEFAULT_EMAIL_TEMPLATE_VARIABLES: list = ["name", "company", "email"]
    DEFAULT_SMS_TEMPLATE_VARIABLES: list = ["name", "phone"]

    # Pagination defaults (non-sensitive)
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()