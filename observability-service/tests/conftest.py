import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def mock_backend_config():
    """Create a mock BackendConfig for testing."""
    from app.tools.base import BackendConfig
    return BackendConfig(
        url="http://localhost:9090",
        auth_type="none",
        credentials=None,
        verify_ssl=False,
        timeout_seconds=5.0
    )
