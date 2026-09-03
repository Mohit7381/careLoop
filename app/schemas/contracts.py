"""
The shared state contract between CareLoop's four agents — v3.

v3 = Mohit's v2 (adopted structurally intact) + the eight alignment decisions
recorded in the TCD, Appendix A ("State-contract alignment", 2026-09-03):

  1. Finding.confidence is Literal["high","medium","low"] — the live sphere
     template (21687 v4) enforces this enum in its strict output schema; a
     float can never arrive from the LLM.
  2. Finding.stage / CodeGap.stage is `str`, validated at the node boundary
     against the ACTIVE journey's routing-table keys (config/journeys/*.yaml)
     via `validate_routing_stage()` — the routing-category CONCEPT is kept
     exactly as v2 designed it; only the vocabulary moves to config (FR9:
     adding a journey is a config drop, zero code change).
  3. RunStatus gains fetching/scanning_code/drafting_prd (UI tracker parity).
  4. RunState gains journey, demo_mode, failed_stage, prev_window_start/end.
  5. gap_class three-way enum is enforced HERE (model_post_init), not in the
     LLM output schema (gpt-5-mini strict mode cannot express nullable enums).
  6. Golden-run target is the PD fixture set (see fixtures/pd_checkout/).
  7. Cohort-cut slices are served by the aggregate() tool directly from
     fixture files — they are NOT carried in Snapshot.
  8. StageDelta gains `maturing` — `delivered` is right-censored (94.5% vs
     69.2% delivered-of-confirmed across the two frozen windows); a naive
     WoW delta reports a phantom "delivery collapse" every week.
  9. CodeGap gains `remedies[]` — the Remedy Loop (2026-09-03): after the
     mechanism is located, a proposer LLM turn suggests <=3 code-verifiable
     remedies; a verifier turn checks each against the source (search) and
     returns exists | absent | partial, iterating once on partial/ambiguous
     results. A remedy verified ABSENT is the strongest PRD input there is;
     one that EXISTS kills a fix-proposal before it embarrasses anyone.

Do not change field names here without syncing with Nakul (Analyst) and
Harshit (Code Scout) — the pipeline validates against these models at each
node boundary.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

FindingOrigin = Literal["warehouse", "voc"]
GapClass = Literal["logic_flaw", "missing_retention_hook", "ux_gap"]
Confidence = Literal["high", "medium", "low"]
RunStatus = Literal[
    "queued", "fetching", "analyzing", "scanning_code",
    "reporting", "drafting_prd", "completed", "failed",
]
NoMatchReason = Literal["no_results", "budget_exhausted", "ambiguous"]
RemedyStatus = Literal["exists", "absent", "partial"]

_GAP_CLASSES = {"logic_flaw", "missing_retention_hook", "ux_gap"}


def validate_routing_stage(stage: str, journey_routing_keys: list[str]) -> str:
    """Boundary check replacing v2's hardcoded RoutingStage Literal (decision #2)."""
    if stage not in journey_routing_keys:
        raise ValueError(
            f"stage '{stage}' is not a routing category of the active journey "
            f"(expected one of {sorted(journey_routing_keys)})"
        )
    return stage


class SegmentFilter(BaseModel):
    dimension: str
    value: str


class EvidenceItem(BaseModel):
    type: str  # "snapshot" | "drilldown"
    metric: str
    value: float


class Finding(BaseModel):
    """Output of Agent 2 (Analyst). Consumed by Agent 3 (Code Scout)."""

    rank: int
    origin: FindingOrigin
    stage: str  # routing category — validate with validate_routing_stage()
    hypothesis: str
    confidence: Confidence
    confirm_via: str

    # warehouse-origin fields
    segments: list[SegmentFilter] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    drilldown_ref: Optional[str] = None

    # voc-origin fields
    theme: Optional[str] = None
    theme_search_terms: list[str] = Field(default_factory=list)
    review_count: Optional[int] = None
    top_quotes: list[str] = Field(default_factory=list)

    def has_citable_evidence(self) -> bool:
        if self.origin == "voc":
            return self.review_count is not None and self.review_count > 0
        return len(self.evidence) > 0


class DrilldownStep(BaseModel):
    question: str
    dimension: str
    result_rows: list[dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


class Remedy(BaseModel):
    """One candidate improvement, proposed from the located mechanism and
    then VERIFIED against the source. `signature` is the code-verifiable
    description the verifier searches for (e.g. "a notification/Garuda call
    inside the abandon batch path")."""

    proposal: str
    signature: str
    search_terms: list[str] = Field(default_factory=list)
    status: Optional[RemedyStatus] = None      # None = not yet verified
    evidence_file: Optional[str] = None        # set when exists/partial
    evidence_line: Optional[int] = None
    evidence_snippet: Optional[str] = None     # cap ~10 lines
    searched_terms: list[str] = Field(default_factory=list)  # audit trail
    iterations: int = 0


class CodeGap(BaseModel):
    finding_rank: int
    origin: FindingOrigin
    stage: str  # routing category — validate with validate_routing_stage()
    service: str
    repo: str

    mechanism_found: bool
    gap_class: Optional[GapClass] = None
    gap_statement: str
    file: Optional[str] = None
    line: Optional[int] = None
    snippet: Optional[str] = None  # cap ~15 lines / 800 chars
    proposed_change_location: Optional[str] = None

    search_terms_used: list[str] = Field(default_factory=list)
    searches_run: int = 0
    no_match_reason: Optional[NoMatchReason] = None

    # Remedy Loop output (decision #9). Only populated when mechanism_found.
    remedies: list[Remedy] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.mechanism_found and self.gap_class is None:
            raise ValueError("gap_class is required when mechanism_found=True")
        if not self.mechanism_found and self.no_match_reason is None:
            raise ValueError("no_match_reason is required when mechanism_found=False")


class StageDelta(BaseModel):
    stage: str
    segment: Optional[str] = None
    previous_rate: float
    current_rate: float
    delta_pp: float
    # Decision #8: right-censored stages (e.g. `delivered`) — the current
    # window hasn't matured; Reporter must exclude or label, never compare raw.
    maturing: bool = False


class AdoptionDelta(BaseModel):
    feature: str
    previous_count: int
    current_count: int
    trend: Literal["faster", "slower", "flat"]


class VocThemeDelta(BaseModel):
    theme: str
    previous_count: int
    current_count: int
    trend: Literal["growing", "shrinking", "flat"]


class TrendReport(BaseModel):
    deltas: list[StageDelta] = Field(default_factory=list)
    adoption: list[AdoptionDelta] = Field(default_factory=list)
    voc_theme_deltas: list[VocThemeDelta] = Field(default_factory=list)
    narrative: str = ""


class VocQuote(BaseModel):
    rating: int
    date: str
    text: str
    theme: str


class Voc(BaseModel):
    reviews_meta: dict[str, Any] = Field(default_factory=dict)
    themes: list[dict[str, Any]] = Field(default_factory=list)
    per_finding_quotes: dict[str, list[VocQuote]] = Field(default_factory=dict)


class SnapshotRow(BaseModel):
    stage: str
    dimension: str
    segment: str
    entered: int
    converted: int
    suppressed: bool = False


class ReasonRow(BaseModel):
    cancellation_reason: str
    cancellation_reason_group: Optional[str] = None
    count: int


class CtEventRow(BaseModel):
    event_name: str
    count: int
    window: Literal["current", "previous"] = "current"


class Snapshot(BaseModel):
    """Output of Agent 1 (Fetcher). Cohort cuts intentionally NOT here (decision #7)."""

    stages: list[SnapshotRow] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    reasons: list[ReasonRow] = Field(default_factory=list)
    ct_events: list[CtEventRow] = Field(default_factory=list)
    previous_stages: list[SnapshotRow] = Field(default_factory=list)


class RunState(BaseModel):
    """The full state object threaded through the LangGraph pipeline."""

    run_id: int
    journey: str = "pd_checkout"          # decision #4
    window_start: str
    window_end: str
    prev_window_start: Optional[str] = None
    prev_window_end: Optional[str] = None
    demo_mode: bool = True
    status: RunStatus = "queued"
    failed_stage: Optional[str] = None    # no-silent-partial-success rule

    snapshot: Snapshot = Field(default_factory=Snapshot)
    findings: list[Finding] = Field(default_factory=list)
    drilldown_trail: list[DrilldownStep] = Field(default_factory=list)
    code_gaps: list[CodeGap] = Field(default_factory=list)
    trend_report: TrendReport = Field(default_factory=TrendReport)
    voc: Voc = Field(default_factory=Voc)
    prd_draft: Optional[str] = None
    artifacts: list[str] = Field(default_factory=list)

    def top_finding(self) -> Optional[Finding]:
        if not self.findings:
            return None
        return sorted(self.findings, key=lambda f: f.rank)[0]

    def gaps_for(self, finding_rank: int) -> list[CodeGap]:
        return [g for g in self.code_gaps if g.finding_rank == finding_rank]
