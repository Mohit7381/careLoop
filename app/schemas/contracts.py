"""
The shared state contract between CareLoop's four agents.

This module is the single source of truth for the shape of `findings[]`
and `code_gaps[]` that cross team boundaries (Analyst -> Code Scout -> Reporter
-> PRD Generator). Do not change field names here without syncing with
Nakul (Analyst) and Harshit (Code Scout) — the pipeline validates against
these models at each node boundary.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

FindingOrigin = Literal["warehouse", "voc"]
GapClass = Literal["logic_flaw", "missing_retention_hook", "ux_gap"]
RunStatus = Literal["queued", "extracting", "analyzing", "reporting", "completed", "failed"]

# Canonical routing-table keys (rev 2, per Harshit) — exact match, no fuzzy substring lookup.
# Finding.stage MUST be one of these; it is a ROUTING CATEGORY, not a funnel-stage id. The
# specific funnel stage (e.g. "payment_processing") lives in the Fetcher's Snapshot and in the
# finding's own hypothesis/evidence text — a finding whose funnel drop is at "payment_processing"
# can still route to stage="consultation" if that's where the owning code actually lives (the
# proven demo example: the abandon-kill script lives in ConsultationDao, not payment-service).
RoutingStage = Literal["consultation", "pharmacy_checkout", "payments", "re_engagement"]
NoMatchReason = Literal["no_results", "budget_exhausted", "ambiguous"]


class SegmentFilter(BaseModel):
    dimension: str
    value: str


class EvidenceItem(BaseModel):
    type: str  # e.g. "snapshot", "drilldown"
    metric: str
    value: float


class Finding(BaseModel):
    """
    Output of Agent 2 (Analyst). Consumed by Agent 3 (Code Scout).

    origin drives which optional fields are populated:
      - "warehouse": segments, evidence, drilldown_ref
      - "voc": theme, theme_search_terms, review_count, top_quotes
    `origin` is also carried through to CodeGap and read by the Reporter, which needs it to
    phrase a finding as a funnel number vs. "N users report X".
    """

    rank: int
    origin: FindingOrigin
    stage: RoutingStage
    hypothesis: str
    confidence: float
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
    """Agent 2 phase-2 whitelisted aggregate() drill-down trail."""

    question: str
    dimension: str
    result_rows: list[dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


class CodeGap(BaseModel):
    """
    Output of Agent 3 (Code Scout). Consumed by Reporter + PRD Generator.

    mechanism_found=False is a first-class outcome (mirrors the Analyst's "insufficient data"
    rule) — gap_class must be null and no_match_reason must be set when that happens. The
    ~5-searches/finding budget is tracked via searches_run for the risk register.
    """

    finding_rank: int
    origin: FindingOrigin
    stage: RoutingStage
    service: str
    repo: str

    mechanism_found: bool
    gap_class: Optional[GapClass] = None  # null when mechanism_found = False
    gap_statement: str
    file: Optional[str] = None
    line: Optional[int] = None
    snippet: Optional[str] = None  # cap ~15 lines / 800 chars — PRD-generation token budget
    proposed_change_location: Optional[str] = None

    search_terms_used: list[str] = Field(default_factory=list)
    searches_run: int = 0
    no_match_reason: Optional[NoMatchReason] = None  # required non-null when mechanism_found = False

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
    """Sits between Code Scout and PRD Generator. Owned by Mohit."""

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
    """Output of Agent 1 (Fetcher). Owned by Alief."""

    stages: list[SnapshotRow] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    reasons: list[ReasonRow] = Field(default_factory=list)
    ct_events: list[CtEventRow] = Field(default_factory=list)
    previous_stages: list[SnapshotRow] = Field(default_factory=list)


class RunState(BaseModel):
    """The full state object threaded through the LangGraph pipeline."""

    run_id: int
    window_start: str
    window_end: str
    status: RunStatus = "queued"

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
