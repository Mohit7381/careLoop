import asyncio
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal, get_session
from app.db.models import AnalysisRun
from app.integrations.garuda_client import GarudaDeliveryError, send_report
from app.pipeline.runner import run_pipeline
from app.agents.scope_resolver import describe, resolve_scope
from app.journeys import load_journey
from app.schemas.api import (CreateRunRequest, CreateRunResponse, DeliverResponse,
                             ResolveScopeRequest, ResolveScopeResponse, RunDetailResponse)
from app.schemas.contracts import RunScope

router = APIRouter(prefix="/v1/analysis", tags=["analysis"])


def require_app_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != settings.app_token:
        raise HTTPException(status_code=401, detail="invalid or missing app token")


def _default_window() -> tuple[str, str]:
    end = datetime.date.today()
    start = end - datetime.timedelta(days=30)
    return start.isoformat(), end.isoformat()


def _run_pipeline_in_new_session(
    run_id: int, window_start: str, window_end: str, demo_mode: bool,
    journey: str, prev_window_start: str | None, prev_window_end: str | None,
    scope: dict | None = None,
) -> None:
    """A background asyncio task needs its own DB session — never share one across threads/tasks."""
    session = SessionLocal()
    try:
        run_pipeline(
            session, run_id, window_start, window_end, demo_mode,
            journey=journey, prev_window_start=prev_window_start,
            prev_window_end=prev_window_end, scope=scope,
        )
    finally:
        session.close()


def _resolve(journey: str, prompt: str | None, dimensions: list[str] | None) -> RunScope:
    """Resolve a prompt against the journey's own vocabulary.

    Explicit `dimensions` win over anything inferred from the prompt — an API
    caller that names them is being specific on purpose.
    """
    cfg = load_journey(journey)
    events = list((cfg.get("event_stage") or {}).keys())
    scope = resolve_scope(prompt or "", cfg, events, cfg["drilldown_dimensions"]) \
        if prompt else RunScope()
    if dimensions:
        scope.dimensions = list(dimensions)
        scope.matched_on.append("dimensions: given explicitly")
    return scope


@router.post("/runs", response_model=CreateRunResponse, dependencies=[Depends(require_app_token)])
async def create_run(body: CreateRunRequest, session: Session = Depends(get_session)) -> CreateRunResponse:
    settings = get_settings()
    window_start, window_end = body.window_start, body.window_end
    if not window_start or not window_end:
        window_start, window_end = _default_window()

    existing = session.execute(
        select(AnalysisRun).where(
            AnalysisRun.journey == body.journey,
            AnalysisRun.window_start == window_start,
            AnalysisRun.window_end == window_end,
            AnalysisRun.status.in_(
                ["queued", "fetching", "analyzing", "scanning_code", "reporting", "drafting_prd"]
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"message": "a run for this window is already in progress", "run_id": existing.id},
        )

    scope = _resolve(body.journey, body.prompt, body.dimensions)
    run = AnalysisRun(
        journey=body.journey,
        window_start=window_start,
        window_end=window_end,
        status="queued",
        config={"dimensions": body.dimensions or [], "scope": scope.model_dump()},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    asyncio.create_task(
        asyncio.to_thread(
            _run_pipeline_in_new_session, run.id, window_start, window_end, settings.demo_mode,
            body.journey, body.prev_window_start, body.prev_window_end, scope.model_dump(),
        )
    )

    return CreateRunResponse(run_id=run.id, status="queued",
                             scope=scope.model_dump(), scope_summary=describe(scope))


@router.post("/runs/resolve-scope", response_model=ResolveScopeResponse,
             dependencies=[Depends(require_app_token)])
def resolve_scope_only(body: ResolveScopeRequest) -> ResolveScopeResponse:
    """Show what a prompt was understood to mean, without running anything.

    Resolution is deliberately deterministic and cheap, so the UI can confirm
    the reading with the user before spending a run on a misinterpretation.
    """
    scope = _resolve(body.journey, body.prompt, None)
    return ResolveScopeResponse(scope=scope.model_dump(), summary=describe(scope),
                                matched_on=scope.matched_on, unresolved=scope.unresolved)


def _read_artifact(run: AnalysisRun, kind: str) -> str | None:
    artifact = next((a for a in run.artifacts if a.kind == kind), None)
    return Path(artifact.uri).read_text() if artifact else None


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: int, session: Session = Depends(get_session)) -> RunDetailResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    return RunDetailResponse(
        run_id=run.id,
        journey=run.journey,
        window_start=run.window_start,
        window_end=run.window_end,
        status=run.status,
        failed_stage=run.failed_stage,
        config=run.config,
        snapshots=[
            {
                "stage": s.stage,
                "dimension": s.dimension,
                "segment": s.segment,
                "entered": s.entered,
                "converted": s.converted,
                "suppressed": s.suppressed,
                "window": s.window,
            }
            for s in run.snapshots
        ],
        findings=[
            {
                "rank": f.rank,
                "origin": f.origin,
                "stage": f.stage,
                "hypothesis": f.hypothesis,
                "segments": f.segments,
                "evidence": f.evidence,
                "confidence": f.confidence,
                "confirm_via": f.confirm_via,
            }
            for f in run.findings
        ],
        code_gaps=run.code_gaps,
        voc=run.voc,
        drilldown_trail=run.drilldown_trail,
        artifacts=[{"kind": a.kind, "uri": a.uri} for a in run.artifacts],
        report_markdown=_read_artifact(run, "report_md"),
        prd_markdown=_read_artifact(run, "prd_md"),
    )


@router.post("/runs/{run_id}/deliver", response_model=DeliverResponse, dependencies=[Depends(require_app_token)])
async def deliver_run(run_id: int, session: Session = Depends(get_session)) -> DeliverResponse:
    """
    The UI's Approve button — pipeline delivery is best-effort/automatic
    (see delivery_node) and reflects nothing about human sign-off; this is
    the explicit "a human clicked Approve" action the plan describes, and
    it's the one real HTTP call the UI's Approve control had nothing to
    hit (screen-2 review, Pritom).
    """
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "completed":
        raise HTTPException(status_code=409, detail=f"run is '{run.status}', not completed — nothing to deliver yet")

    report_md = _read_artifact(run, "report_md")
    if report_md is None:
        raise HTTPException(status_code=404, detail="no report generated for this run")

    try:
        send_report(
            run_id=run.id,
            report_summary=report_md[:500],
            report_link=f"/v1/analysis/runs/{run.id}/report",
            prd_link=f"/v1/analysis/runs/{run.id}" if _read_artifact(run, "prd_md") else None,
        )
        return DeliverResponse(run_id=run.id, delivered=True, detail="sent")
    except GarudaDeliveryError as exc:
        return DeliverResponse(run_id=run.id, delivered=False, detail=f"Garuda not configured or unreachable: {exc}")


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: int, session: Session = Depends(get_session)) -> str:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    report = next((a for a in run.artifacts if a.kind == "report_md"), None)
    if report is None:
        raise HTTPException(status_code=404, detail="report not generated yet for this run")

    return Path(report.uri).read_text()


@router.get("/runs/{run_id}/prd")
async def get_run_prd(run_id: int, session: Session = Depends(get_session)) -> str:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    prd = next((a for a in run.artifacts if a.kind == "prd_md"), None)
    if prd is None:
        raise HTTPException(status_code=404, detail="no PRD drafted for this run's top finding yet")

    return Path(prd.uri).read_text()
