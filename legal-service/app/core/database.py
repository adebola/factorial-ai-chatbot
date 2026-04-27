import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/legal_db"
)

VECTOR_DATABASE_URL = os.environ.get(
    "VECTOR_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/vector_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=300,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000"
    }
)

engine_vector = create_engine(
    VECTOR_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=300,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=60000"
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
VectorSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_vector)
Base = declarative_base()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_vector_db():
    """FastAPI dependency for vector database sessions."""
    db = VectorSessionLocal()
    try:
        yield db
    finally:
        db.close()
