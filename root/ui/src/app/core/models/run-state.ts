/**
 * TypeScript mirror of app/schemas/contracts.py ("CareLoop — Shared State
 * Contract v2"). Field names and shapes here MUST match that file exactly —
 * it is the single source of truth shared across all four agents. Do not
 * rename anything here without syncing with Nakul/Harshit, same as the
 * Python side.
 *
 * RunStatus is intentionally the SAME six-value enum as contracts.py. It has
 * no per-stage state (see StageKey below and RunStageView in run.service.ts
 * for how the UI derives four stage cards from this one field).
 */

export type FindingOrigin = 'warehouse' | 'voc';
export type GapClass = 'logic_flaw' | 'missing_retention_hook' | 'ux_gap';
export type RunStatus = 'queued' | 'extracting' | 'analyzing' | 'reporting' | 'completed' | 'failed';

/** Rev 3 (2026-09-03) — Code Scout's output shape. Replaces CodeGap, kept
 *  below for reference only (contracts.py keeps it too, marked SUPERSEDED).
 *  "business"/"process" carry no code evidence at all — this is generative
 *  ("what could we build/change here") not diagnostic ("find the one bug"),
 *  so a Finding can produce zero to several Suggestions. */
export type SuggestionType = 'tech' | 'business' | 'process';
export type VerificationStatus = 'exists' | 'absent' | 'partial' | 'not_applicable';

/** Routing category — NOT a funnel-stage id. Exact-match key into the Code
 *  Scout routing table (bintan/consultation, timor/oms, ...). A finding's
 *  funnel-stage name lives in its own hypothesis/evidence text instead. */
export type RoutingStage = 'consultation' | 'pharmacy_checkout' | 'payments' | 're_engagement';
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
  confidence: number;
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

/** SUPERSEDED (Rev 3) — see Suggestion below. Kept for reference only;
 *  Code Scout no longer produces this shape as of the explore-and-suggest
 *  flow, but contracts.py keeps the class (and this mirror does too) for
 *  git-history / comparison, same as the Python side.
 *
 *  Output of Agent 3 (Code Scout). Consumed by Reporter + PRD Generator.
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
}

/** PROVISIONAL (Rev 3) — Code Scout's actual output as of 2026-09-03,
 *  replacing CodeGap. A Finding can produce zero to several Suggestions
 *  (generative: propose improvements/new features, not diagnostic: find the
 *  one bug). suggestion_type is not limited to code — "business" and
 *  "process" are equally valid and carry no code evidence.
 *
 *  verification_status only applies to suggestion_type="tech" — mirrors
 *  contracts.py's Suggestion.model_post_init:
 *    - non-"tech" types must be "not_applicable"
 *    - "exists"/"partial" require evidence_file
 *  "absent" means "we checked this file and didn't find it," not "unknown"
 *  — evidence_file is still set in that case, evidence_line is not. */
export interface Suggestion {
  finding_rank: number;
  origin: FindingOrigin;
  stage: RoutingStage;
  service: string;
  repo: string;

  suggestion_type: SuggestionType;
  title: string;
  description: string;
  rationale: string;

  verification_status: VerificationStatus;
  evidence_file?: string | null;
  evidence_line?: number | null;

  search_terms_used?: string[];
  searches_run?: number;
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

/** The full state object threaded through the LangGraph pipeline —
 *  identical shape to Python's RunState. Fetched from
 *  GET /v1/analysis/runs/{id}. */
export interface RunState {
  run_id: number;
  window_start: string;
  window_end: string;
  status: RunStatus;

  snapshot: Snapshot;
  findings: Finding[];
  drilldown_trail: DrilldownStep[];
  code_gaps: CodeGap[]; // SUPERSEDED (Rev 3) — see suggestions
  suggestions: Suggestion[]; // PROVISIONAL (Rev 3)
  trend_report: TrendReport;
  voc: Voc;
  prd_draft: string | null;
  artifacts: string[];
}
