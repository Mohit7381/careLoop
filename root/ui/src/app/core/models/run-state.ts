/**
 * TypeScript mirror of `app/schemas/contracts.py` on `main` (contracts v3).
 * Field names and shapes here MUST match that file exactly —
 * it is the single source of truth shared across all four agents. Do not
 * rename anything here without syncing with Nakul/Harshit, same as the
 * Python side.
 *
 * RunStatus is intentionally the SAME six-value enum as contracts.py. It has
 * no per-stage state (see StageKey below and RunStageView in run.service.ts
 * for how the UI derives four stage cards from this one field).
 */

export type FindingOrigin = 'warehouse' | 'voc';
export type GapClass = 'logic_flaw' | 'missing_retention_hook' | 'ux_gap' | 'unclassified';
export type RunStatus =
  | 'queued' | 'fetching' | 'analyzing' | 'scanning_code'
  | 'reporting' | 'drafting_prd' | 'completed' | 'failed';

/** Was a float in v2; the backend now sends a literal. */
export type Confidence = 'high' | 'medium' | 'low';

/** Remedy Loop verdict. `null` on the wire means NOT YET VERIFIED, which is
 *  a different claim from "absent" — see Remedy.status. */
export type RemedyStatus = 'exists' | 'absent' | 'partial';

/** Routing category — NOT a funnel-stage id. Exact-match key into the Code
 *  Scout routing table (bintan/consultation, timor/oms, ...). A finding's
 *  funnel-stage name lives in its own hypothesis/evidence text instead. */
/** Routing category — NOT a funnel-stage id. These are the keys under
 *  `routing:` in `config/journeys/pd_checkout.yaml`, and the VoC lexicon in
 *  that same file routes themes to `delivery` and `stock` too, so a data
 *  refresh can produce them. Kept as a widened string so an unknown category
 *  from a future journey renders rather than failing to type-check. */
export type RoutingStage =
  | 'consultation' | 'pharmacy_checkout' | 'payments'
  | 'delivery' | 'stock' | 're_engagement'
  | (string & {});
export type NoMatchReason = 'no_results' | 'budget_exhausted' | 'ambiguous';

export interface SegmentFilter {
  dimension: string;
  value: string;
}

export interface EvidenceItem {
  type: string; // e.g. "snapshot", "drilldown"
  metric: string;
  value: number;
}

/** Output of Agent 2 (Analyst). Consumed by Agent 3 (Code Scout).
 *  origin drives which optional fields are populated:
 *    - "warehouse": segments, evidence, drilldown_ref
 *    - "voc": theme, theme_search_terms, review_count, top_quotes         */
export interface Finding {
  rank: number;
  origin: FindingOrigin;
  stage: RoutingStage;
  hypothesis: string;
  confidence: Confidence;
  confirm_via: string;

  segments?: SegmentFilter[];
  evidence?: EvidenceItem[];
  drilldown_ref?: string | null;

  theme?: string | null;
  theme_search_terms?: string[];
  review_count?: number | null;
  top_quotes?: string[];
}

/** Agent 2 phase-2 whitelisted aggregate() drill-down trail. */
export interface DrilldownStep {
  question: string;
  dimension: string;
  result_rows?: Record<string, unknown>[];
  note?: string | null;
}

/** Output of Agent 3 (Code Scout). Consumed by Reporter + PRD Generator.
 *  mechanism_found=false is a first-class outcome, not an error — gap_class
 *  is null and no_match_reason is required in that case (contracts.py
 *  enforces this with model_post_init; mirror the same either/or on read). */
export interface CodeGap {
  finding_rank: number;
  origin: FindingOrigin;
  stage: RoutingStage;
  service: string;
  repo: string;

  mechanism_found: boolean;
  gap_class: GapClass | null;
  gap_statement: string;
  file?: string | null;
  line?: number | null;
  snippet?: string | null;
  proposed_change_location?: string | null;

  search_terms_used?: string[];
  searches_run?: number;
  no_match_reason?: NoMatchReason | null;
  /** Remedy Loop output — only populated when mechanism_found is true. */
  remedies?: Remedy[];
}

/** One proposed, code-verified fix inside a CodeGap (Remedy Loop, rev 2.1).
 *  `signature` is what the loop searched for to decide `status`. */
export interface Remedy {
  proposal: string;
  signature: string;
  /** null/undefined = the loop did not get to verify this one. Distinct from
   *  'absent' ("we searched and it is not there") — rendering them alike was
   *  PR #5 B3. */
  status?: RemedyStatus | null;
  evidence_file?: string | null;
  evidence_line?: number | null;
  evidence_snippet?: string | null;
  search_terms?: string[];
  /** Audit trail of what was actually searched — used to say how many
   *  searches backed an 'absent'. */
  searched_terms?: string[];
  iterations?: number;
}

export interface StageDelta {
  stage: string;
  segment?: string | null;
  previous_rate: number;
  current_rate: number;
  delta_pp: number;
}

export interface AdoptionDelta {
  feature: string;
  previous_count: number;
  current_count: number;
  trend: 'faster' | 'slower' | 'flat';
}

export interface VocThemeDelta {
  theme: string;
  previous_count: number;
  current_count: number;
  trend: 'growing' | 'shrinking' | 'flat';
}

/** Sits between Code Scout and PRD Generator. Owned by Mohit. */
export interface TrendReport {
  deltas: StageDelta[];
  adoption: AdoptionDelta[];
  voc_theme_deltas: VocThemeDelta[];
  narrative: string;
}

export interface VocQuote {
  rating: number;
  date: string;
  text: string;
  theme: string;
}

export interface Voc {
  reviews_meta: Record<string, unknown>;
  themes: Record<string, unknown>[];
  per_finding_quotes: Record<string, VocQuote[]>;
}

export interface SnapshotRow {
  stage: string;
  dimension: string;
  segment: string;
  entered: number;
  converted: number;
  suppressed?: boolean;
}

export interface ReasonRow {
  cancellation_reason: string;
  cancellation_reason_group?: string | null;
  count: number;
}

export interface CtEventRow {
  event_name: string;
  count: number;
  window: 'current' | 'previous';
}

/** Output of Agent 1 (Fetcher). Owned by Alief. */
export interface Snapshot {
  stages: SnapshotRow[];
  segments: string[];
  reasons: ReasonRow[];
  ct_events: CtEventRow[];
  previous_stages: SnapshotRow[];
}

/**
 * What GET /v1/analysis/runs/{id} actually returns — `RunDetailResponse` in
 * app/schemas/api.py, which is NOT the pipeline's internal RunState:
 *  - `snapshots` is a flat array (with a `window` discriminator), not
 *    `snapshot.stages`
 *  - it carries `journey`, `failed_stage`, `config`
 *  - the markdown artifacts arrive inline as report_markdown / prd_markdown
 * Mapped onto the view model by RunService; see the adapter there.
 */
export interface RunDetailResponse {
  run_id: number;
  journey: string;
  window_start: string;
  window_end: string;
  status: RunStatus;
  failed_stage?: string | null;
  config: Record<string, unknown>;
  snapshots: (SnapshotRow & { window?: 'current' | 'previous' })[];
  findings: Finding[];
  code_gaps: CodeGap[];
  voc: Voc;
  drilldown_trail: DrilldownStep[];
  artifacts: { kind: string; uri: string }[];
  report_markdown?: string | null;
  prd_markdown?: string | null;
}

/** The view model the components render. */
export interface RunState {
  run_id: number;
  window_start: string;
  window_end: string;
  status: RunStatus;

  snapshot: Snapshot;
  findings: Finding[];
  drilldown_trail: DrilldownStep[];
  /** Agent 3's output, with Remedy Loop verdicts nested per gap. */
  code_gaps: CodeGap[];
  trend_report: TrendReport;
  voc: Voc;
  prd_draft: string | null;
  artifacts: string[];
}
