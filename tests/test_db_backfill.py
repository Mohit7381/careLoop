"""init_db must bring an older careloop.db up to the current model shape.

create_all never alters an existing table, so every column added to a model
after the first release needs an _ensure_column line — this test builds the
pre-#6 run_artifacts shape and checks old rows survive the upgrade."""
import sqlite3

from sqlalchemy import create_engine, inspect

import app.db.base as base


def test_old_run_artifacts_shape_is_upgraded(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE run_artifacts (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, "
                "kind VARCHAR(32) NOT NULL, uri TEXT NOT NULL)")
    con.execute("INSERT INTO run_artifacts (run_id, kind, uri) VALUES (1, 'report_md', 'x.md')")
    con.commit(); con.close()

    # init_db and _ensure_column both read the module-level engine; swap it for
    # this test only (monkeypatch restores it) instead of reloading the module.
    monkeypatch.setattr(base, "engine", create_engine(f"sqlite:///{db}", future=True))
    base.init_db()

    cols = {c["name"] for c in inspect(base.engine).get_columns("run_artifacts")}
    assert {"finding_rank", "title", "edited", "edited_at"} <= cols
    with base.engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT run_id, kind, edited FROM run_artifacts").fetchone()
    assert tuple(row) == (1, "report_md", 0)          # old rows survive, default applied
    base.init_db()                                     # idempotent
