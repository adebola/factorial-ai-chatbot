from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

# Load database URLs from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@localhost/chatbot_db")
VECTOR_DATABASE_URL = os.environ.get("VECTOR_DATABASE_URL", "postgresql://postgres:password@localhost:5432/vector_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

engine_vector = create_engine(VECTOR_DATABASE_URL, echo=False)
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

