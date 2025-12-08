from sqlalchemy import create_engine, QueuePool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from .config import settings
import os

from .logging_config import get_logger
import logging

logger = get_logger("database")

# Load database URLs from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost/onboard_db")
VECTOR_DATABASE_URL = os.environ.get("VECTOR_DATABASE_URL", "postgresql://postgres:password@localhost:5432/vector_db")

# Main database with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.POOL_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.POOL_RECYCLE_SECONDS,
    pool_timeout=settings.POOL_TIMEOUT,
    connect_args={
        "connect_timeout": settings.CONNECT_TIMEOUT,
        "options": "-c statement_timeout=30000"  # 30 seconds
    }
)

engine_vector = create_engine(
    VECTOR_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=settings.POOL_RECYCLE_SECONDS,
    pool_timeout=settings.POOL_TIMEOUT,
    connect_args={
        "connect_timeout": settings.CONNECT_TIMEOUT,
        "options": "-c statement_timeout=30000"  # 30 seconds
    },
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal_vector = sessionmaker(autocommit=False, autoflush=False, bind=engine_vector)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    except Exception as e:
        logger.error(f"Main Database session error {e}")
        db.rollback()
        raise  # Re-raise the exception so FastAPI can handle it properly
    finally:
        db.close()

def get_vector_db() -> Generator[Session, None, None]:
    vector_db = SessionLocal_vector()

    try:
        yield vector_db
    except Exception as e:
        logger.error(f"Vector Database session error {e}")
        vector_db.rollback()
        raise  # Re-raise the exception so FastAPI can handle it properly
    finally:
        vector_db.close()