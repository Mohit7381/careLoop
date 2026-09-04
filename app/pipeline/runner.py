"""
Orchestrator glue. OWNER: Mohit.

Owns the bits LangGraph itself doesn't: DB status transitions, persisting
snapshots/findings/artifacts once the graph finishes, and turning any node
exception into a `failed` run instead of a crashed background task.
"""
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AnalysisRun, DropOffFinding, FunnelSnapshot, RunArtifact
from app.pipeline.graph import compiled_graph
from app.pipeline.state import initial_state

logger = logging.getLogger("careloop.runner")


def _persist_snapshot(session: Session, run_id: int, snapshot: dict, window: str) -> None:
    for row in snapshot.get("stages" if window == "current" else "previous_stages", []):
        session.add(
            FunnelSnapshot(
                run_id=run_id,
                stage=row["stage"],
                dimension=row.get("dimension", "overall"),
                segment=row.get("segment", "all"),
                entered=row["entered"],
                converted=row["converted"],
                suppressed=row.get("suppressed", False),
                window=window,
            )
        )


def _persist_findings(session: Session, run_id: int, findings: list[dict]) -> None:
    for f in findings:
        session.add(
            DropOffFinding(
                run_id=run_id,
                rank=f["rank"],
                origin=f["origin"],
                stage=f["stage"],
                hypothesis=f["hypothesis"],
                segments=f["segments"],
                evidence=f["evidence"],
                confidence=f["confidence"],
                confirm_via=f["confirm_via"],
            )
        )


def _persist_artifacts(session: Session, run_id: int, state: dict) -> None:
    settings = get_settings()
    run_dir = Path(settings.artifacts_dir) / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    for artifact in state.get("artifacts", []):
        if artifact["kind"] != "report_md":
            continue
        path = run_dir / "report.md"
        path.write_text(artifact["content"])
        session.add(RunArtifact(run_id=run_id, kind="report_md", uri=str(path)))

    if state.get("prd_draft"):
        path = run_dir / "prd.md"
        path.write_text(state["prd_draft"])
        session.add(RunArtifact(run_id=run_id, kind="prd_md", uri=str(path)))


def run_pipeline(
    session: Session,
    run_id: int,
    window_start: str,
    window_end: str,
    demo_mode: bool,
    journey: str = "pd_checkout",
    prev_window_start: str | None = None,
    prev_window_end: str | None = None,
    scope: dict | None = None,
) -> None:
    """Synchronous — call via asyncio.to_thread from the API layer so the endpoint returns immediately."""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        logger.error("run_pipeline called for unknown run_id=%s", run_id)
        return

    try:
        state = initial_state(
            run_id, window_start, window_end, demo_mode,
            journey=journey, prev_window_start=prev_window_start,
            prev_window_end=prev_window_end, scope=scope,
        )
        # Stream node by node so the run's status is persisted as each stage
        # finishes. invoke() only returned at the end, so a live run sat at
        # "queued" for its whole ten minutes while the UI polled — the row said
        # nothing had started when three stages were already done.
        # Persist each stage's output as it lands, not only at the end. The
        # detail page polls this run while it is in flight; with everything
        # persisted at the end it showed an empty funnel and no findings for
        # the whole run, and one UI bug turned that emptiness into stale
        # fixture data under the live run's header. Now the funnel appears
        # after the Fetcher, findings after the Analyst, gaps after Code Scout.
        persisted = {"snapshot": False, "findings": False, "gaps": False}
        final_state = state
        for final_state in compiled_graph.stream(state, stream_mode="values"):
            new_status = final_state.get("status")
            if new_status and new_status != run.status and new_status not in ("completed", "failed"):
                run.status = new_status
            snap = final_state.get("snapshot") or {}
            if not persisted["snapshot"] and snap.get("stages"):
                _persist_snapshot(session, run_id, snap, "current")
                _persist_snapshot(session, run_id, snap, "previous")
                persisted["snapshot"] = True
            if not persisted["findings"] and final_state.get("findings"):
                _persist_findings(session, run_id, final_state["findings"])
                run.drilldown_trail = final_state.get("drilldown_trail", [])
                run.voc = final_state.get("voc", {})
                run.findings_rejected = final_state.get("findings_rejected", [])
                persisted["findings"] = True
            if not persisted["gaps"] and final_state.get("code_gaps"):
                run.code_gaps = final_state["code_gaps"]
                persisted["gaps"] = True
            session.commit()

        if final_state.get("error"):
            logger.warning("run %s finished with a recorded error: %s", run_id, final_state["error"])

        if not persisted["snapshot"]:
            _persist_snapshot(session, run_id, final_state.get("snapshot", {}), "current")
            _persist_snapshot(session, run_id, final_state.get("snapshot", {}), "previous")
        if not persisted["findings"]:
            _persist_findings(session, run_id, final_state.get("findings", []))
        _persist_artifacts(session, run_id, final_state)

        run.status = final_state.get("status", "completed")
        run.failed_stage = final_state.get("failed_stage")
        run.code_gaps = final_state.get("code_gaps", [])
        run.voc = final_state.get("voc", {})
        run.drilldown_trail = final_state.get("drilldown_trail", [])
        run.findings_rejected = final_state.get("findings_rejected", [])
        session.commit()
    except Exception:
        logger.exception("run %s failed", run_id)
        run.status = "failed"
        session.commit()
        raise
