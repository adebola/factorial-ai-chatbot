from sqlalchemy import create_engine, QueuePool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

# Load database URLs from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@localhost/chatbot_db")
VECTOR_DATABASE_URL = os.environ.get("VECTOR_DATABASE_URL", "postgresql://postgres:password@localhost:5432/vector_db")

# Main database with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,  # Recycle connections every 5 minutes
    pool_timeout=30,   # Wait max 30 seconds for connection
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000"  # 30 seconds
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Vector database with connection pooling
engine_vector = create_engine(
    VECTOR_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,  # Recycle connections every 5 minutes
    pool_timeout=30,   # Wait max 30 seconds for connection
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000"  # 30 seconds
    },
    echo=False
)

SessionLocal_vector = sessionmaker(autocommit=False, autoflush=False, bind=engine_vector)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_vector_db() -> Generator[Session, None, None]:
    try:
        vector_db = SessionLocal_vector()
        yield vector_db
    finally:
        vector_db.close()
