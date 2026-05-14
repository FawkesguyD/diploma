from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://realestate:realestate@localhost:5432/realestate"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine(database_url: str | None = None):
    return create_engine(database_url or get_database_url(), pool_pre_ping=True)


engine = create_db_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
