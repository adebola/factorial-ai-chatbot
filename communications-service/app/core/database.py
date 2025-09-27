import os
from typing import Any, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Get database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.environ.get("POOL_SIZE", "10")),
    max_overflow=int(os.environ.get("POOL_MAX_OVERFLOW", "20")),
    pool_recycle=int(os.environ.get("POOL_RECYCLE_SECONDS", "3600")),
    pool_pre_ping=True,  # Validate connections before use
    echo=False  # Set to True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, Any, None]:
    """
    Dependency to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Create all tables in the database
    Use this for initial setup
    """
    from ..models.communications import Base
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """
    Drop all tables in the database
    Use this for testing or database reset
    """
    from ..models.communications import Base
    Base.metadata.drop_all(bind=engine)