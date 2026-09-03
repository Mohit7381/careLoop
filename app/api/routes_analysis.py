import asyncio
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal, get_session
from app.db.models import AnalysisRun
from app.pipeline.runner import run_pipeline
from app.schemas.api import CreateRunRequest, CreateRunResponse, RunDetailResponse

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
) -> None:
    """A background asyncio task needs its own DB session — never share one across threads/tasks."""
    session = SessionLocal()
    try:
        run_pipeline(
            session, run_id, window_start, window_end, demo_mode,
            journey=journey, prev_window_start=prev_window_start, prev_window_end=prev_window_end,
        )
    finally:
        session.close()


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

    run = AnalysisRun(
        journey=body.journey,
        window_start=window_start,
        window_end=window_end,
        status="queued",
        config={"dimensions": body.dimensions or []},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    asyncio.create_task(
        asyncio.to_thread(
            _run_pipeline_in_new_session, run.id, window_start, window_end, settings.demo_mode,
            body.journey, body.prev_window_start, body.prev_window_end,
        )
    )

    return CreateRunResponse(run_id=run.id, status="queued")


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
        artifacts=[{"kind": a.kind, "uri": a.uri} for a in run.artifacts],
    )


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: int, session: Session = Depends(get_session)) -> str:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    report = next((a for a in run.artifacts if a.kind == "report_md"), None)
    if report is None:
        raise HTTPException(status_code=404, detail="report not generated yet for this run")

    return Path(report.uri).read_text()
