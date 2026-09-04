import asyncio
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal, get_session
from app.db.models import AnalysisRun, RunArtifact
from app.agents.scope_resolver import describe, pick_journey, resolve_scope
from app.integrations.garuda_client import GarudaDeliveryError, send_report
from app.journeys import all_journeys, load_journey
from app.pipeline.prd_editor import apply_edit_instruction
from fastapi.concurrency import run_in_threadpool
from app.pipeline.runner import run_pipeline
from app.schemas.api import (
    CreateRunRequest,
    CreateRunResponse,
    DeliverResponse,
    PrdChatRequest,
    PrdChatResponse,
    PrdSummary,
    ResolveScopeRequest,
    ResolveScopeResponse,
    RunDetailResponse,
    ScopeChatRequest,
    ScopeChatResponse,
)
from app.schemas.contracts import RunScope
from app.scope_resolver import resolve_dimensions

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
    requested_dimensions: list[str] | None = None,
) -> None:
    """A background asyncio task needs its own DB session — never share one across threads/tasks."""
    session = SessionLocal()
    try:
        run_pipeline(
            session, run_id, window_start, window_end, demo_mode,
            journey=journey, prev_window_start=prev_window_start, prev_window_end=prev_window_end,
            scope=scope, requested_dimensions=requested_dimensions,
        )
    finally:
        session.close()


def find_duplicate_run(in_flight, prompt: str | None):
    """The run already in flight that asks the SAME question, or None.

    Runs are prompt-scoped, so the duplicate key is (journey, window, prompt),
    not (journey, window). Keying on the window alone returned 409 for a user
    asking a different question about the same week while another run was
    still going — three times in one session.
    """
    wanted = (prompt or "").strip().lower()
    for run in in_flight:
        theirs = (((run.config or {}).get("scope") or {}).get("prompt") or "").strip().lower()
        if theirs == wanted:
            return run
    return None


def _pick_journey(journey: str | None, prompt: str | None) -> tuple[str, list[str]]:
    """'auto' (or empty) picks the journey from the prompt's own vocabulary."""
    if journey and journey != "auto":
        return journey, []
    return pick_journey(prompt or "", all_journeys())


def _resolve(journey: str, prompt: str | None) -> RunScope:
    """Resolve a prompt against the journey's own vocabulary.

    `CreateRunRequest.dimensions` is deliberately NOT folded in here. That
    field names ROUTING CATEGORIES (payments, consultation, ...) and is a
    post-run filter on which findings surface — Mohit's PR #9. `scope.dimensions`
    names DRILL-DOWN CUTS (stock_status, item_count, ...) and narrows what the
    Analyst explores. The two vocabularies are disjoint, so copying one into the
    other either 422s at his validator or empties the AggregateTool whitelist.
    A caller can use both: scope the run from the entry page, then filter the
    report to a category.
    """
    if not prompt:
        return RunScope()
    cfg = load_journey(journey)
    events = list((cfg.get("event_stage") or {}).keys())
    return resolve_scope(prompt, cfg, events, cfg["drilldown_dimensions"])


def _validate_dimensions(journey: str, dimensions: list[str] | None) -> list[str]:
    """
    Prompt-scoped analysis (decision #13, contracts.py): `dimensions` names
    routing categories from the journey's own `routing:` table (e.g.
    "payments", "consultation") — not arbitrary strings. Refused here, at
    request time, rather than silently running unscoped or producing a
    confusing zero-findings run with no explanation of why.
    """
    if not dimensions:
        return []
    valid = set(load_journey(journey)["routing"].keys())
    unknown = [d for d in dimensions if d not in valid]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"unknown dimension(s) for journey '{journey}': {', '.join(unknown)}",
                "valid_dimensions": sorted(valid),
            },
        )
    return dimensions


@router.post("/scope/chat", response_model=ScopeChatResponse)
async def scope_chat(body: ScopeChatRequest) -> ScopeChatResponse:
    """
    The "confirm with the user" half of prompt-scoped analysis (decision
    #13): resolves free text ("analyze cart abandonment dropoff") to the
    structured `dimensions` list POST /runs already accepts, WITHOUT
    creating a run — a caller shows `reply`/`dimensions` back to the user
    for confirmation, then calls POST /runs with the confirmed list. Never
    mutates anything, so unlike the run-creation and PRD-chat-edit
    endpoints this doesn't need the app token.
    """
    dimensions, reply = resolve_dimensions(body.journey, body.message)
    return ScopeChatResponse(dimensions=dimensions, reply=reply, resolved=bool(dimensions))


@router.post("/runs", response_model=CreateRunResponse, dependencies=[Depends(require_app_token)])
async def create_run(body: CreateRunRequest, session: Session = Depends(get_session)) -> CreateRunResponse:
    settings = get_settings()
    window_start, window_end = body.window_start, body.window_end
    if not window_start or not window_end:
        window_start, window_end = _default_window()

    journey, journey_hits = _pick_journey(body.journey, body.prompt)
    # Validated against the RESOLVED journey, not body.journey — "auto" is not
    # a real journey to load a routing table for, and a caller who names both
    # a journey and dimensions still means those dimensions against whichever
    # journey actually gets picked.
    dimensions = _validate_dimensions(journey, body.dimensions)
    scope = _resolve(journey, body.prompt)
    if journey_hits:
        scope.matched_on.insert(0, f"journey:{journey} (via {', '.join(journey_hits[:3])})")
    in_flight = session.execute(
        select(AnalysisRun).where(
            AnalysisRun.journey == journey,
            AnalysisRun.window_start == window_start,
            AnalysisRun.window_end == window_end,
            AnalysisRun.status.in_(
                ["queued", "fetching", "analyzing", "scanning_code", "reporting", "drafting_prd"]
            ),
        )
    ).scalars().all()
    existing = find_duplicate_run(in_flight, scope.prompt)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"message": "the same question is already running for this window",
                    "run_id": existing.id},
        )

    run = AnalysisRun(
        journey=journey,
        window_start=window_start,
        window_end=window_end,
        status="queued",
        config={"dimensions": dimensions, "scope": scope.model_dump()},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    asyncio.create_task(
        asyncio.to_thread(
            _run_pipeline_in_new_session, run.id, window_start, window_end, settings.demo_mode,
            journey, body.prev_window_start, body.prev_window_end, scope.model_dump(), dimensions,
        )
    )

    return CreateRunResponse(run_id=run.id, status="queued", journey=journey,
                             scope=scope.model_dump(), scope_summary=describe(scope))


@router.post("/runs/resolve-scope", response_model=ResolveScopeResponse,
             dependencies=[Depends(require_app_token)])
def resolve_scope_only(body: ResolveScopeRequest) -> ResolveScopeResponse:
    """Show what a prompt was understood to mean, without running anything.

    Resolution is deliberately deterministic and cheap, so the UI can confirm
    the reading with the user before spending a run on a misinterpretation.
    """
    journey, journey_hits = _pick_journey(body.journey, body.prompt)
    scope = _resolve(journey, body.prompt)
    if journey_hits:
        scope.matched_on.insert(0, f"journey:{journey} (via {', '.join(journey_hits[:3])})")
    return ResolveScopeResponse(scope=scope.model_dump(), summary=describe(scope, journey),
                                matched_on=scope.matched_on, unresolved=scope.unresolved, journey=journey)


def _read_artifact(run: AnalysisRun, kind: str) -> str | None:
    artifact = next((a for a in run.artifacts if a.kind == kind), None)
    return Path(artifact.uri).read_text() if artifact else None


def _prd_artifact(run: AnalysisRun, finding_rank: int) -> RunArtifact | None:
    return next((a for a in run.artifacts if a.kind == "prd_md" and a.finding_rank == finding_rank), None)


def _rank1_prd_markdown(run: AnalysisRun) -> str | None:
    a = _prd_artifact(run, 1)
    return Path(a.uri).read_text() if a else None


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
        scope=(run.config or {}).get("scope"),
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
                "journey_events": f.journey_events,
                "drilldown_ref": f.drilldown_ref,
                "theme": f.theme,
                "theme_search_terms": f.theme_search_terms,
                "review_count": f.review_count,
                "top_quotes": f.top_quotes,
            }
            for f in run.findings
        ],
        code_gaps=run.code_gaps,
        suggestions=run.suggestions,
        voc=run.voc,
        drilldown_trail=run.drilldown_trail,
        findings_rejected=run.findings_rejected or [],
        artifacts=[{"kind": a.kind, "uri": a.uri} for a in run.artifacts],
        report_markdown=_read_artifact(run, "report_md"),
        prd_markdown=_rank1_prd_markdown(run),
        prds=[
            # prd_md rows written before #6 have no finding_rank; they were always
            # the #1 finding's PRD, so read them back as rank 1 instead of 500-ing
            # every GET for an older run.
            PrdSummary(finding_rank=a.finding_rank if a.finding_rank is not None else 1,
                       title=a.title, markdown=Path(a.uri).read_text(), edited=bool(a.edited))
            for a in sorted((a for a in run.artifacts if a.kind == "prd_md"), key=lambda a: a.finding_rank or 1)
        ],
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
            prd_link=f"/v1/analysis/runs/{run.id}" if _rank1_prd_markdown(run) else None,
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
async def get_run_prd(
    run_id: int, rank: int = Query(default=1, ge=1), session: Session = Depends(get_session)
) -> str:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    prd = _prd_artifact(run, rank)
    if prd is None:
        raise HTTPException(status_code=404, detail=f"no PRD drafted for finding #{rank} on this run")

    return Path(prd.uri).read_text()


def _prd_edit_llm(run: AnalysisRun):
    """Live sphere only. Demo mode replays a recorded *generation*, which would
    silently replace the reviewer's PRD with a different document — so without
    LIVE_LLM there is no model here and the editor says so."""
    from app.integrations.sphere import _live_llm_wanted, make_use_case_llm
    if not _live_llm_wanted(True):
        return None
    return make_use_case_llm(get_settings().llm_use_case_prd_generation, demo_mode=False, journey=run.journey)


@router.post(
    "/runs/{run_id}/prd/{rank}/chat",
    response_model=PrdChatResponse,
    dependencies=[Depends(require_app_token)],
)
async def chat_edit_prd(
    run_id: int, rank: int, body: PrdChatRequest, session: Session = Depends(get_session)
) -> PrdChatResponse:
    """
    Chat-style editing for a drafted PRD — a human asks for a change in
    plain language instead of hand-editing markdown. See
    app/pipeline/prd_editor.py for exactly what it can and can't do
    autonomously; it's honest about the difference rather than faking a
    full LLM rewrite.
    """
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    artifact = _prd_artifact(run, rank)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"no PRD drafted for finding #{rank} on this run")

    current = Path(artifact.uri).read_text()
    # A rewrite is a 30-50 s sphere call; keep it off the event loop so
    # polling GETs keep answering while the reviewer waits.
    result = await run_in_threadpool(apply_edit_instruction, current, body.message, _prd_edit_llm(run))

    Path(artifact.uri).write_text(result.markdown)
    artifact.edited = True
    artifact.edited_at = datetime.datetime.utcnow()
    session.commit()

    return PrdChatResponse(finding_rank=rank, reply=result.reply, markdown=result.markdown, applied=result.applied)
