from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.db import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _ensure_column("analysis_runs", "findings_rejected", "JSON NOT NULL DEFAULT '[]'")


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """create_all never alters an existing table. Until a migration tool
    lands, add a missing column in place so an existing careloop.db keeps
    working after a pull. Idempotent; SQLite and MySQL both accept the form."""
    from sqlalchemy import inspect, text
    if column in {c["name"] for c in inspect(engine).get_columns(table)}:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
