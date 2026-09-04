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
    # create_all never alters an existing table, so every column added to a
    # model after its table already existed in someone's local careloop.db
    # needs a manual backfill here until a real migration tool lands.
    _ensure_column("analysis_runs", "findings_rejected", "JSON NOT NULL DEFAULT '[]'")
    _ensure_column("analysis_runs", "suggestions", "JSON NOT NULL DEFAULT '[]'")
    _ensure_column("drop_off_findings", "journey_events", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column("drop_off_findings", "drilldown_ref", "TEXT")
    _ensure_column("drop_off_findings", "theme", "VARCHAR(128)")
    _ensure_column("drop_off_findings", "theme_search_terms", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column("drop_off_findings", "review_count", "INTEGER")
    _ensure_column("drop_off_findings", "top_quotes", "TEXT NOT NULL DEFAULT '[]'")
    # #6 multi-PRD: run_artifacts gained per-finding columns; an existing local
    # careloop.db raised "no such column: run_artifacts.finding_rank" on the
    # first run after pulling main.
    _ensure_column("run_artifacts", "finding_rank", "INTEGER")
    _ensure_column("run_artifacts", "title", "TEXT")
    _ensure_column("run_artifacts", "edited", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("run_artifacts", "edited_at", "DATETIME")


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
