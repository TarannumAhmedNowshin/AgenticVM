"""SQLAlchemy engine, session factory, and declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, sessionmaker
from sqlalchemy.orm import Mapped
from sqlalchemy.sql import func

from backend.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Declarative base with sensible defaults."""


class TimestampMixin:
    """Adds created_at / updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a scoped session and closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
