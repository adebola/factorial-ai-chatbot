"""Shared pytest fixtures for communications-service tests.

In-memory SQLite database + dependency overrides keep tests hermetic. The
WhatsApp tests in particular exercise real SQL (UNIQUE constraints,
idempotency, multi-tenant isolation) so a real engine — not just a Mock — is
required.
"""
import os
import sys
from typing import Generator

# Set required env vars BEFORE any `app.*` import — several modules read these
# at import time and raise if missing.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("WHATSAPP_PROVIDER", "mock")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")
os.environ.setdefault("CHAT_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("BILLING_SERVICE_URL", "http://localhost:8005")
os.environ.setdefault("AUTHORIZATION_SERVER_URL", "http://localhost:9000")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# Make the service package importable when pytest is invoked from this dir.
SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Brand-new in-memory SQLite session per test.

    Uses StaticPool so the same connection is reused across the session,
    which is required for SQLite's in-memory mode to share schema between
    different sessionmaker instances.
    """
    from app.models.communications import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
