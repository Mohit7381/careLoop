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

v3.1 (PR #3 rebase, 2026-09-03): two additive decisions, neither touching
the CodeGap/Remedy shape above:
  10. RunState gets `model_config = ConfigDict(extra="forbid")`. Without it,
      pydantic's default extra="ignore" silently drops any field a caller
      sends that this model doesn't declare - the PR #3 review reproduced
      this live (a real Analyst handoff payload lost journey/demo_mode/
      prev_window_start/prev_window_end/failed_stage with no error).
      journey is the serious one: it's the key that resolves routing, so
      losing it means nothing downstream can re-derive where a finding
      belongs. Silent loss is worse than a crash.
  11. Finding gains `journey_events` and CodeGap/RunState gain the
      Suggestion/SuggestionType/VerificationStatus family - Code Scout's
      alternate "explore the repo, then propose tech/business/process
      improvements" output shape (PR #3's Rev 3), kept ADDITIVE alongside
      CodeGap/Remedy rather than replacing it. Whether Suggestion replaces
      CodeGap.remedies, sits alongside it, or doesn't ship is an explicit
      three-way call (Nakul/Mohit/Harshit) per the PR #3 review (S2) - this
      file makes room for either answer without forcing one.

Do not change field names here without syncing with Nakul (Analyst) and
Harshit (Code Scout) — the pipeline validates against these models at each
node boundary.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

FindingOrigin = Literal["warehouse", "voc"]
# "unclassified": the mechanism WAS located (file:line) but the model's class
# was not one of the three and could not be mapped, or the assessment call
# failed outright. It exists so a found mechanism is never reported as
# mechanism_found=False — a live run did exactly that nine times out of nine.
GapClass = Literal["logic_flaw", "missing_retention_hook", "ux_gap", "unclassified"]
Confidence = Literal["high", "medium", "low"]
RunStatus = Literal[
    "queued", "fetching", "analyzing", "scanning_code",
    "reporting", "drafting_prd", "completed", "failed",
]
NoMatchReason = Literal["no_results", "budget_exhausted", "ambiguous"]
RemedyStatus = Literal["exists", "absent", "partial"]

SuggestionType = Literal["tech", "business", "process"]
# "not_applicable" = nothing to verify (business/process, or tech with no
# signature). "unverified" = there WAS something to verify but we didn't -
# budget exhausted, or the verification call itself failed. Conflating the
# two misreports "we didn't check" as "there was nothing to check" (review S3).
VerificationStatus = Literal["exists", "absent", "partial", "not_applicable", "unverified"]

_GAP_CLASSES = {"logic_flaw", "missing_retention_hook", "ux_gap", "unclassified"}


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

    # Decision #11 - the real analytics event names bounding the drop-off.
    # Not code identifiers, but far better search-term seed material than
    # parsing free-text hypothesis prose. Additive - defaults to empty, so
    # existing findings/fixtures that don't set it are unaffected.
    journey_events: list[str] = Field(default_factory=list)

    # warehouse-origin fields
    segments: list[SegmentFilter] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    drilldown_ref: Optional[str] = None

    # voc-origin fields
    theme: Optional[str] = None
    theme_search_terms: list[str] = Field(default_factory=list)
    review_count: Optional[int] = None
    top_quotes: list[str] = Field(default_factory=list)

    # PROPOSED (2026-09-04, needs Nakul's sign-off - same additive treatment
    # journey_events got before confirmation). Set only when `theme` was
    # attached by phase3_voc.correlate_with_llm()'s reasoned match rather
    # than corroborate()'s stage-equality lookup - the evidence-discipline
    # this whole system runs on means a reasoned claim needs to show its
    # work, not just silently populate theme/review_count.
    correlation_rationale: Optional[str] = None

    def has_citable_evidence(self) -> bool:
        if self.origin == "voc":
            return self.review_count is not None and self.review_count > 0
        return len(self.evidence) > 0


GrowthIdeaInspiration = Literal["funnel_data", "positive_review", "industry_pattern"]


class GrowthIdea(BaseModel):
    """Analyst phase 2 (2026-09-04): a proactive, forward-looking idea for
    GROWING transactions — distinct from Finding, which diagnoses a loss.
    Produced only on the drill-down's concluding turn, alongside findings.

    Three inspirations, in decreasing order of grounding:
    "funnel_data": a specific funnel number the model was shown this run —
      either top_gap (what's broken) or top_strength / a drilldown_trail row
      (what already converts well, so an idea can build on a proven part of
      the funnel instead of only reacting to the loss). Evidence is required
      and held to the same verbatim-citation discipline as Finding.evidence.
    "positive_review": a positive_voc_signals theme count — what users
      already praise in reviews (2026-09-04: the VoC pipeline classifies
      POSITIVE reviews, not just complaints, for exactly this). Evidence is
      required the same way.
    "industry_pattern": the model's own general knowledge of digital health /
      e-commerce / fintech products, NOT a live web search (this pipeline has
      no browsing tool) — evidence must stay empty; the prompt is the
      enforcement point for "never fabricate a source". This model only
      enforces that evidence-or-not tracks the inspiration, since a
      fabricated citation cannot be told apart from a real one by shape
      alone.
    """

    title: str
    description: str
    rationale: str
    inspiration: GrowthIdeaInspiration
    target_stage: Optional[str] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.inspiration in ("funnel_data", "positive_review") and not self.evidence:
            raise ValueError(f"a {self.inspiration} growth idea needs at least one evidence item")
        if self.inspiration == "industry_pattern" and self.evidence:
            raise ValueError(
                "an industry_pattern growth idea must carry no evidence — it is not "
                "grounded in this run's own data and must never look like it is"
            )


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

    def model_post_init(self, __context: Any) -> None:
        # A verdict of exists/partial is a claim about specific source. If we
        # cannot name the file, we have not earned the claim — the honest
        # states are "absent" (searched, not found) or None (unverified).
        # Adopted from Harshit's Suggestion model; the Remedy Loop's verify
        # path was hardened to satisfy this rather than the reverse.
        if self.status in ("exists", "partial") and not self.evidence_file:
            raise ValueError(
                f"evidence_file is required when status is {self.status!r}"
            )


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


class Suggestion(BaseModel):
    """Decision #11 - Code Scout's alternate output shape (Rev 3): explore a
    routing-matched repo to inventory what already exists, then propose
    improvements - NOT limited to code. "business"/"process" suggestions are
    equally valid and carry no code evidence. Kept additive alongside
    CodeGap/Remedy; see this file's module docstring.

    A Finding can produce zero to several Suggestions - generative (propose
    improvements/new features), not diagnostic (find the one bug).
    verification_status only applies to suggestion_type="tech" - checked
    within the specific inventory file the suggestion is grounded in (not a
    whole-repo search, which false-positives when unrelated infrastructure
    for the same capability exists elsewhere in the service).
    """

    finding_rank: int
    origin: FindingOrigin
    stage: str  # routing category — validate with validate_routing_stage()
    service: str
    repo: str

    suggestion_type: SuggestionType
    title: str
    description: str
    rationale: str  # why this addresses the drop-off - ties back to the finding

    verification_status: VerificationStatus = "not_applicable"
    evidence_file: Optional[str] = None
    evidence_line: Optional[int] = None

    search_terms_used: list[str] = Field(default_factory=list)
    searches_run: int = 0

    def model_post_init(self, __context: Any) -> None:
        if self.suggestion_type != "tech" and self.verification_status != "not_applicable":
            raise ValueError("verification_status only applies to suggestion_type='tech'")
        if self.verification_status in ("exists", "partial") and self.evidence_file is None:
            raise ValueError("evidence_file is required when verification_status is exists/partial")


class ShippedCommit(BaseModel):
    """One commit, as attributed by GitLab blame on a remedy's evidence line."""

    sha: str
    short_sha: str
    author: str
    date: str            # commit's committed_date, ISO 8601
    message: str
    web_url: Optional[str] = None


class ShippedFix(BaseModel):
    """Closed-loop impact (2026-09-04): a Remedy the Remedy Loop verified
    `exists` whose evidence line's last commit (GitLab blame) landed after
    this run's own baseline (`prev_window_end`, or `window_start` when no
    explicit baseline was given) — i.e. code that was proposed/would have
    been proposed as a fix has since actually shipped. Code Scout only ever
    sets the commit-attribution fields (finding_rank..commit); it never
    invents a metric. Reporter fills metric_name/metric_unit/previous_value/
    current_value/pct_change/metric_ref *after* the fact, from a TrendReport
    delta row it already computed independently — matching the existing
    "correlation, never causation" discipline: this records that a fix
    shipped and a metric moved in the same window, not that one caused the
    other.
    """

    finding_rank: int
    origin: FindingOrigin
    stage: str
    repo: str
    remedy_proposal: str
    evidence_file: str
    evidence_line: int
    evidence_snippet: Optional[str] = None  # from the Remedy that shipped, for explore_shipped_feature
    commit: ShippedCommit

    metric_name: Optional[str] = None
    metric_unit: Optional[str] = None       # "%" | "events"
    previous_value: Optional[float] = None
    current_value: Optional[float] = None
    pct_change: Optional[float] = None      # relative change: (current-previous)/previous*100
    metric_ref: Optional[str] = None        # the TrendReport delta row id this came from

    def model_post_init(self, __context: Any) -> None:
        metric_fields = (self.metric_name, self.metric_unit, self.previous_value,
                         self.current_value, self.pct_change, self.metric_ref)
        if any(f is not None for f in metric_fields) and not all(f is not None for f in metric_fields):
            raise ValueError(
                "ShippedFix metric fields must all be set together or not at all — "
                "Reporter fills all six once a matching trend delta exists, never a partial subset"
            )


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


class RunScope(BaseModel):
    """What a user asked for, resolved into constraints the pipeline can obey.

    A free-text prompt must never reach the Analyst as prose: phase1.largest_drop
    is deterministic, and that is load-bearing — it is why the headline number
    cannot be argued into existence. So a prompt is resolved into this, shown
    back to the user, and then applied as constraints.

    Every field is optional; an unscoped run leaves them all None and behaves
    exactly as before.

    `dimensions` here names DRILL-DOWN CUTS (stock_status, item_count, ...) and
    narrows what the Analyst explores — disjoint from RunState.requested_dimensions
    below, which names ROUTING CATEGORIES (payments, consultation, ...) and is a
    post-run filter on which findings surface. See routes_analysis.py's `_resolve`.
    """

    prompt: Optional[str] = None            # what the user actually typed
    from_stage: Optional[str] = None        # target transition, overriding largest_drop
    to_stage: Optional[str] = None
    dimensions: list[str] = Field(default_factory=list)   # restrict the drill-down
    review_days: Optional[int] = None       # "the last 10-15 days of reviews"
    matched_on: list[str] = Field(default_factory=list)   # why the resolver chose this
    unresolved: list[str] = Field(default_factory=list)   # asked for, could not honour

    def is_scoped(self) -> bool:
        return bool(self.from_stage or self.dimensions or self.review_days)
class PrdDraft(BaseModel):
    """One PRD, tied to the finding it was drafted for (decision #12: more
    than one finding can produce a PRD in the same run — up to
    MAX_PRDS_PER_RUN in prd_generator.py — not just the #1 ranked one)."""

    finding_rank: int
    title: str
    markdown: str
    source: str = "deterministic"   # "llm" | "deterministic" | why the model draft was rejected


class RunState(BaseModel):
    """The full state object threaded through the LangGraph pipeline.

    extra="forbid" (decision #10): pydantic's own default (extra="ignore")
    silently dropped journey/demo_mode/prev_window_start/prev_window_end/
    failed_stage in a narrower, independently-drifted RunState during PR #3's
    review - losing `journey` is the serious one, since it's the key that
    resolves routing, so nothing downstream could re-derive where a finding
    belonged. Silent loss is worse than a crash; forbid so the next contract
    drift fails loudly instead.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: int
    journey: str = "pd_checkout"          # decision #4
    window_start: str
    window_end: str
    prev_window_start: Optional[str] = None
    prev_window_end: Optional[str] = None
    demo_mode: bool = True
    status: RunStatus = "queued"
    failed_stage: Optional[str] = None    # no-silent-partial-success rule

    scope: RunScope = Field(default_factory=RunScope)
    # Decision #13 - prompt-scoped analysis: a caller can ask for one or
    # more routing categories instead of the full journey (POST /runs
    # {"dimensions": ["payments"]}). Validated against the journey's own
    # `routing:` keys at request time (routes_analysis.py), so an unknown
    # category is refused before a run is ever created rather than silently
    # producing zero findings. Applied as a post-filter in analyst_node -
    # narrows what surfaces, not how the Analyst explores. Disjoint from
    # scope.dimensions above (see RunScope's own docstring).
    requested_dimensions: list[str] = Field(default_factory=list)

    snapshot: Snapshot = Field(default_factory=Snapshot)
    findings: list[Finding] = Field(default_factory=list)
    # Findings the evidence gate refused, with the reason. A run that ends with
    # zero warehouse findings must be able to say why — a live run once dropped
    # its only finding ("insufficient data", prose evidence) in total silence.
    findings_rejected: list[dict[str, Any]] = Field(default_factory=list)
    drilldown_trail: list[DrilldownStep] = Field(default_factory=list)
    growth_ideas: list[GrowthIdea] = Field(default_factory=list)  # phase 2's concluding-turn output
    code_gaps: list[CodeGap] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)  # decision #11
    shipped_fixes: list[ShippedFix] = Field(default_factory=list)  # closed-loop impact (2026-09-04)
    # explore_shipped_feature output (2026-09-04): follow-on ideas built forward
    # from a shipped fix with a positive measured outcome. Reuses the Suggestion
    # shape from decision #11 — same evidence discipline, different trigger
    # (a win, not a drop-off) — kept in its own list so it never collides with
    # code_scout's own (not-yet-decided) `suggestions` output.
    feature_amplifications: list[Suggestion] = Field(default_factory=list)
    trend_report: TrendReport = Field(default_factory=TrendReport)
    voc: Voc = Field(default_factory=Voc)
    prd_draft: Optional[str] = None                              # #1 finding's PRD only — kept for back-compat
    prd_drafts: list[PrdDraft] = Field(default_factory=list)      # one per finding — decision #12, NEW
    prd_source: str = "deterministic"   # how the #1 draft was produced: llm | deterministic | rejection reason
    artifacts: list[str] = Field(default_factory=list)

    def top_finding(self) -> Optional[Finding]:
        if not self.findings:
            return None
        return sorted(self.findings, key=lambda f: f.rank)[0]

    def gaps_for(self, finding_rank: int) -> list[CodeGap]:
        return [g for g in self.code_gaps if g.finding_rank == finding_rank]

    def suggestions_for(self, finding_rank: int) -> list[Suggestion]:
        return [s for s in self.suggestions if s.finding_rank == finding_rank]
