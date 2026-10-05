"""SQLAlchemy database setup (SQLite locally, PostgreSQL on AWS/RDS)."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine() -> "Engine":  # noqa: F821
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    settings.ensure_dirs()
    from . import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    """FastAPI dependency."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
