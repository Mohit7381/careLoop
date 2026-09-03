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
    _backfill_drop_off_finding_columns()


def _backfill_drop_off_finding_columns() -> None:
    """
    create_all() only creates missing TABLES, not columns added to an
    existing table's model — there's no Alembic here, just create_all,
    which is fine until a table's shape changes under it. drop_off_findings
    picked up 6 columns (journey_events, drilldown_ref, theme,
    theme_search_terms, review_count, top_quotes) after runs already
    existed on the old 8-column shape, so existing local DBs need these
    added in place rather than losing prior run data to a fresh create_all.
    Sqlite-only: no other backend is in use for this project.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "journey_events": "TEXT NOT NULL DEFAULT '[]'",
        "drilldown_ref": "TEXT",
        "theme": "VARCHAR(128)",
        "theme_search_terms": "TEXT NOT NULL DEFAULT '[]'",
        "review_count": "INTEGER",
        "top_quotes": "TEXT NOT NULL DEFAULT '[]'",
    }
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(drop_off_findings)")}
        for column, ddl_type in additions.items():
            if column in existing:
                continue
            conn.exec_driver_sql(f"ALTER TABLE drop_off_findings ADD COLUMN {column} {ddl_type}")
        conn.commit()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
