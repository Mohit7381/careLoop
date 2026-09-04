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


def test_legacy_prd_artifact_without_rank_is_served_as_rank_1(tmp_path):
    """A prd_md artifact row from before #6 (finding_rank NULL) must not make
    GET /runs/{id} fail validation; it is the #1 finding's PRD."""
    from fastapi.testclient import TestClient
    from app.db import models
    from app.db.base import SessionLocal, init_db
    from app.main import app

    init_db()
    prd = tmp_path / "prd.md"; prd.write_text("# legacy prd")
    with SessionLocal() as s:
        run = models.AnalysisRun(journey="pd_checkout", window_start="2026-08-01", window_end="2026-08-07",
                                 status="completed")
        s.add(run); s.flush()
        s.add(models.RunArtifact(run_id=run.id, kind="prd_md", uri=str(prd), finding_rank=None, title=None))
        s.commit(); run_id = run.id

    r = TestClient(app).get(f"/v1/analysis/runs/{run_id}")
    assert r.status_code == 200, r.text
    assert [(p["finding_rank"], p["markdown"]) for p in r.json()["prds"]] == [(1, "# legacy prd")]
