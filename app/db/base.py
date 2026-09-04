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
    _backfill_analysis_run_columns()


def _backfill_analysis_run_columns() -> None:
    """
    create_all() only creates missing TABLES, not columns added to an
    existing table's model — there's no Alembic here, just create_all.
    analysis_runs picked up `suggestions` (Code Scout's alternate tech/
    business/process flow, contracts.py decision #11) after runs already
    existed on the old shape; backfill it in place on sqlite rather than
    losing prior run data to a fresh create_all. Sqlite-only: no other
    backend is in use for this project.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(analysis_runs)")}
        if "suggestions" not in existing:
            conn.exec_driver_sql("ALTER TABLE analysis_runs ADD COLUMN suggestions TEXT NOT NULL DEFAULT '[]'")
        conn.commit()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
