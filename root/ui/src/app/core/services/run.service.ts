import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { EMPTY, Subscription, firstValueFrom, timer } from 'rxjs';
import { catchError, switchMap, tap, timeout } from 'rxjs/operators';

import { RUN_47_RESPONSE } from '../fixtures/run-47.fixture';
import { PrdSummary, RunDetailResponse, RunState, RunStatus, SnapshotRow } from '../models/run-state';
import { environment } from '../../../environments/environment';

export type StageKey = 'fetch' | 'analyze' | 'code' | 'prd';
export type StageStatus = 'pending' | 'running' | 'done' | 'failed';

export interface StageView {
  key: StageKey;
  label: string;
  status: StageStatus;
  summary: string;
}

/** `live-failed` covers every reason the live source was abandoned — the
 *  specific reason is in `liveError`, because "unreachable" was wrong for
 *  most of them (a 404 or a stale-contract payload is not unreachable). */
export type Source = 'fixture' | 'live' | 'live-failed';

/** POST /v1/analysis/runs/resolve-scope — the backend's reading of a prompt. */
export interface ResolvedScope {
  scope: {
    prompt?: string | null;
    from_stage?: string | null;
    to_stage?: string | null;
    dimensions?: string[];
    review_days?: number | null;
  };
  summary: string;
  matched_on: string[];
  unresolved: string[];
  /** Which journey the prompt was understood to be about (picked from the prompt when 'auto'). */
  journey?: string;
}

const STAGE_LABELS: Record<StageKey, string> = {
  fetch: 'FETCH DATA',
  analyze: 'ANALYZE DROP-OFFS',
  code: 'SCAN SERVICE CODE',
  prd: 'DRAFT PRD',
};

/**
 * Derives the four stage cards from RunState.status.
 *
 * contracts.py's RunStatus is ONE global field, not per-stage state:
 *   queued | extracting | analyzing | reporting | completed | failed
 *
 * Two stages can never show "running" on the live feed as a result:
 * `reporting` jumps SCAN SERVICE CODE straight to done, and nothing
 * distinguishes PRD drafting from "reporting" finishing. The fixture
 * animation (RunPlaybackService) fakes real per-stage timing for the demo;
 * this map is what the LIVE path is actually limited to today.
 *
 * Raise adding `scanning` / `drafting` to RunStatus with Mohit before
 * relying on live per-stage progress for the "money moment" reveal.
 */
const STATUS_MAP: Record<Exclude<RunStatus, 'failed'>, StageStatus[]> = {
  queued: ['pending', 'pending', 'pending', 'pending'],
  fetching: ['running', 'pending', 'pending', 'pending'],
  analyzing: ['done', 'running', 'pending', 'pending'],
  scanning_code: ['done', 'done', 'running', 'pending'],
  reporting: ['done', 'done', 'done', 'running'],
  drafting_prd: ['done', 'done', 'done', 'running'],
  completed: ['done', 'done', 'done', 'done'],
};

const STAGE_KEYS: StageKey[] = ['fetch', 'analyze', 'code', 'prd'];
const POLL_MS = 1500;
const REQUEST_TIMEOUT_MS = 10_000;
// A PRD rewrite is a real model call on the backend (30-50 s); the generic
// request timeout would abandon it while it is still working.
const PRD_CHAT_TIMEOUT_MS = 90_000;
const DELIVER_TIMEOUT_MS = 8_000;
const MAX_RETRIES = 2;
const API_BASE = '/v1/analysis/runs';
// POST routes require Bearer auth (backend .env -> APP_TOKEN). Read from the
// Angular environment so there is no path where a real token is committed
// alongside the source.
const APP_TOKEN = environment.appToken;

/**
 * Runtime shape check on the polled payload.
 *
 * `http.get<T>()` is a compile-time assertion, not a guarantee. This checks
 * the fields the UI actually dereferences, so a backend on an older contract
 * fails loudly and visibly rather than half-rendering: without it, a missing
 * array makes a computed throw, Angular keeps the last good value, and the
 * screen shows the LIVE header over FIXTURE data with the chip still reading
 * "live" — every number belonging to a different run than the header claims.
 */
function validateRunDetail(body: unknown): { ok: true; run: RunDetailResponse } | { ok: false; reason: string } {
  if (!body || typeof body !== 'object') return { ok: false, reason: 'response was not an object' };
  const r = body as Partial<RunDetailResponse>;

  if (typeof r.run_id !== 'number') return { ok: false, reason: 'missing run_id' };
  if (typeof r.status !== 'string') return { ok: false, reason: 'missing status' };
  if (!Array.isArray(r.snapshots)) {
    return {
      ok: false,
      reason: (r as { snapshot?: unknown }).snapshot
        ? 'backend is on the old contract (snapshot.stages, not snapshots[])'
        : 'missing snapshots[]',
    };
  }
  if (!Array.isArray(r.findings)) return { ok: false, reason: 'missing findings[]' };
  if (!Array.isArray(r.code_gaps)) return { ok: false, reason: 'missing code_gaps[] — backend predates the Remedy Loop API' };
  if (!Array.isArray(r.drilldown_trail)) return { ok: false, reason: 'missing drilldown_trail[]' };
  if (!r.voc || typeof r.voc !== 'object') return { ok: false, reason: 'missing voc' };

  return { ok: true, run: body as RunDetailResponse };
}

/**
 * RunDetailResponse -> the view model the components render.
 *
 * The ONLY place API field names are touched. Two shape differences worth
 * naming: `snapshots` is flat with a `window` discriminator (so the current
 * window has to be filtered out of it), and the markdown artifacts arrive
 * inline rather than needing a second fetch.
 */
function toRunState(r: RunDetailResponse): RunState {
  const current = r.snapshots.filter((s) => (s.window ?? 'current') === 'current');
  const previous = r.snapshots.filter((s) => s.window === 'previous');
  return {
    run_id: r.run_id,
    journey: r.journey,
    window_start: r.window_start,
    window_end: r.window_end,
    status: r.status,
    snapshot: {
      stages: current as SnapshotRow[],
      segments: [],
      reasons: [],
      ct_events: [],
      previous_stages: previous as SnapshotRow[],
    },
    findings: r.findings ?? [],
    drilldown_trail: r.drilldown_trail ?? [],
    code_gaps: r.code_gaps ?? [],
    suggestions: r.suggestions ?? [],
    trend_report: { deltas: [], adoption: [], voc_theme_deltas: [], narrative: '' },
    // An in-flight run returns `voc: {}` — Phase 3 has not run yet.
    // validateRunDetail only proves `voc` is an object, not that it is
    // populated, so default each field here and every consumer can read the
    // shape unconditionally instead of guarding at each call site.
    voc: {
      reviews_meta: r.voc?.reviews_meta ?? {},
      themes: r.voc?.themes ?? [],
      per_finding_quotes: r.voc?.per_finding_quotes ?? {},
    },
    prd_draft: r.prd_markdown ?? null,
    prds: r.prds ?? [],
    artifacts: (r.artifacts ?? []).map((a) => a.uri),
  };
}

/** Transient = worth retrying. A 404 or a 4xx is not going to fix itself. */
function isTransient(err: unknown): boolean {
  if (!(err instanceof HttpErrorResponse)) return true; // timeout / unknown -> retry once
  return err.status === 0 || err.status >= 500;
}

function describeError(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) return 'backend unreachable';
    if (err.status === 404) return 'run not found (404)';
    if (err.status >= 500) return `backend error (${err.status})`;
    return `request rejected (${err.status})`;
  }
  return 'request timed out';
}

@Injectable({ providedIn: 'root' })
export class RunService {
  private readonly http = inject(HttpClient);

  private readonly _run = signal<RunState>(toRunState(RUN_47_RESPONSE));
  private readonly _source = signal<Source>('fixture');
  private readonly _liveError = signal<string | null>(null);
  private readonly _polling = signal(false);
  private pollSub: Subscription | null = null;

  readonly run = this._run.asReadonly();
  readonly source = this._source.asReadonly();
  /** Why the live source was abandoned — null unless source is 'live-failed'. */
  readonly liveError = this._liveError.asReadonly();
  readonly polling = this._polling.asReadonly();

  /** Set only by DemoPlaybackService, to drive the four stage cards through
   *  timed beats for the fixture-mode "Replay run" animation — real
   *  per-stage timing that RunStatus alone cannot express (see the class
   *  doc on STATUS_MAP). null = fall through to the status-derived view. */
  private readonly _demoOverride = signal<StageView[] | null>(null);

  readonly stages = computed<StageView[]>(() => {
    const override = this._demoOverride();
    if (override) return override;

    const run = this._run();
    const statuses = run.status === 'failed' ? this.failedStatuses(run) : STATUS_MAP[run.status];
    return STAGE_KEYS.map((key, i) => ({
      key,
      label: STAGE_LABELS[key],
      status: statuses[i],
      summary: this.summaryFor(key, run, statuses[i]),
    }));
  });

  /** Reveal gates for demo playback — which run panels are visible right
   *  now. Defaults to "everything visible" (status-derived) so the page
   *  always loads at rest, per the reveal rule: nothing waits on an
   *  observer or a click to become visible for the first time. */
  private readonly _revealOverride = signal<{ funnel: boolean; findings: boolean; code: boolean } | null>(null);
  readonly reveal = computed(() => this._revealOverride() ?? { funnel: true, findings: true, code: true });

  /** How many drilldown_trail rows are visible right now, and how many the
   *  Analyst stage reports as "used" while running. null = all visible. */
  private readonly _trailProgress = signal<number | null>(null);
  readonly trailVisibleCount = computed(() => this._trailProgress() ?? this._run().drilldown_trail.length);

  setStageOverride(view: StageView[] | null): void {
    this._demoOverride.set(view);
  }
  setReveal(reveal: { funnel: boolean; findings: boolean; code: boolean } | null): void {
    this._revealOverride.set(reveal);
  }
  setTrailProgress(count: number | null): void {
    this._trailProgress.set(count);
  }

  /** Loads the frozen fixture. This is the default and the demo-safe path —
   *  it never depends on network or a live run existing. */
  loadFixture(): void {
    this.stopPolling();
    this._source.set('fixture');
    this._liveError.set(null);
    this._run.set(toRunState(RUN_47_RESPONSE));
    this._demoOverride.set(null);
    this._revealOverride.set(null);
    this._trailProgress.set(null);
  }

  /**
   * Switches to polling GET /v1/analysis/runs/{id} every 1.5s until the run
   * reaches completed|failed.
   *
   * Failure handling, in order:
   *  - transient errors (network down, 5xx, timeout) retry up to MAX_RETRIES
   *    with a linear backoff, because one blip should not permanently kill
   *    the live view;
   *  - anything that survives that, plus any 4xx and any payload failing
   *    validateRunState(), falls back to the fixture and records WHY in
   *    `liveError` so the chip can say something true rather than
   *    "unreachable" for a 404 or a contract mismatch.
   *
   * The fixture fallback is deliberate: on stage, a readable screen with an
   * honest "showing fixture, here's why" chip beats a blank or half-rendered
   * one. What it must never do is show live and fixture data mixed together.
   */
  goLive(runId: number): void {
    this.stopPolling();

    if (!Number.isInteger(runId) || runId <= 0) {
      this.failLive(`invalid run id "${runId}"`);
      return;
    }

    this._source.set('live');
    this._liveError.set(null);
    this._polling.set(true);

    // Retries ride on the poll timer itself rather than a nested retry()
    // operator: a backoff longer than POLL_MS would be cancelled mid-flight
    // by switchMap on the next tick, so the failure path never runs and the
    // backend gets hammered forever. Counting consecutive failures instead
    // gives the same "survive a blip" behaviour at exactly the poll cadence.
    let consecutiveFailures = 0;

    this.pollSub = timer(0, POLL_MS)
      .pipe(
        switchMap(() =>
          this.http.get<unknown>(`${API_BASE}/${runId}`).pipe(
            timeout(REQUEST_TIMEOUT_MS),
            catchError((err) => {
              consecutiveFailures++;
              if (isTransient(err) && consecutiveFailures <= MAX_RETRIES) {
                return EMPTY; // skip this tick; the timer retries on the next one
              }
              this.failLive(describeError(err));
              return EMPTY;
            })
          )
        ),
        tap((body) => {
          const result = validateRunDetail(body);
          if (!result.ok) {
            // A malformed payload is not transient — no point retrying it.
            this.failLive(result.reason);
            return;
          }
          consecutiveFailures = 0;
          this._run.set(toRunState(result.run));
          if (result.run.status === 'completed' || result.run.status === 'failed') {
            this.stopPolling();
          }
        })
      )
      .subscribe();
  }

  /**
   * POST /v1/analysis/runs/resolve-scope — what a prompt is understood to mean,
   * without running anything.
   *
   * Separate from createRun on purpose: resolution is deterministic and cheap,
   * so the reading can be confirmed before a run is spent on a misreading. An
   * unresolvable prompt is not an error — it means the full funnel is analysed,
   * and the summary says so.
   */
  async resolveScope(prompt: string, journey = 'auto'): Promise<ResolvedScope | { error: string }> {
    try {
      return await firstValueFrom(
        this.http
          .post<ResolvedScope>(
            `${API_BASE}/resolve-scope`,
            { journey, prompt },
            { headers: { Authorization: `Bearer ${APP_TOKEN}` } }
          )
          .pipe(timeout(REQUEST_TIMEOUT_MS))
      );
    } catch (err) {
      return { error: err instanceof HttpErrorResponse ? describeError(err) : 'request timed out' };
    }
  }

  /** A one-shot read for the dashboard's row, without starting the poller. */
  async fetchRun(runId: number): Promise<RunDetailResponse | null> {
    try {
      const body = await firstValueFrom(
        this.http.get<unknown>(`${API_BASE}/${runId}`).pipe(timeout(REQUEST_TIMEOUT_MS))
      );
      const result = validateRunDetail(body);
      return result.ok ? result.run : null;
    } catch {
      return null;
    }
  }

  /**
   * POST /v1/analysis/runs — kicks off a real pipeline run.
   *
   * Requires the app token (GET does not). A 409 means a run for this window
   * is already in progress and carries that run's id in `detail.run_id`, so
   * the caller can attach to it instead of dead-ending — which is what
   * happens if someone clicks "New analysis" twice.
   */
  async createRun(
    journey = 'auto',
    prompt?: string
  ): Promise<{ runId: number; existing: boolean; scopeSummary?: string; journey?: string } | { error: string }> {
    try {
      const res = await firstValueFrom(
        this.http
          .post<{ run_id: number; status: RunStatus; scope_summary?: string; journey?: string }>(
            API_BASE,
            prompt ? { journey, prompt } : { journey },
            { headers: { Authorization: `Bearer ${APP_TOKEN}` } }
          )
          .pipe(timeout(REQUEST_TIMEOUT_MS))
      );
      return { runId: res.run_id, existing: false, scopeSummary: res.scope_summary, journey: res.journey };
    } catch (err) {
      if (err instanceof HttpErrorResponse) {
        const detail = err.error?.detail;
        if (err.status === 409 && typeof detail?.run_id === 'number') {
          return { runId: detail.run_id, existing: true };
        }
        if (err.status === 401) return { error: 'not authorised — check APP_TOKEN' };
        if (err.status === 422) {
          const msg = typeof detail === 'string' ? detail : 'unknown dimension for this journey';
          return { error: `scope rejected — ${msg}` };
        }
        return { error: describeError(err) };
      }
      return { error: 'request timed out' };
    }
  }

  /** Abandon the live source, say why, and show the fixture — never a mix. */
  private failLive(reason: string): void {
    this._source.set('live-failed');
    this._liveError.set(reason);
    this._run.set(toRunState(RUN_47_RESPONSE));
    this.stopPolling();
  }

  stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
    this._polling.set(false);
  }

  /**
   * POST /v1/analysis/runs/{id}/deliver.
   *
   * No UI surface calls this today — the "Approve & send to GChat" button was
   * removed from the PRD drawer. Kept because the endpoint is real and
   * documented, so a delivery affordance can return without re-deriving the
   * client. Delete it if delivery is dropped for good.
   *
   * Historic note on the shape below: it was written when this
   * backend (not in the API table in the PRD). Optimistic by design: the
   * caller shows its own success state immediately and calls this in the
   * background, so a slow or dead Garuda/GChat integration can never
   * produce a dead moment on stage. See README "Known gaps — GChat
   * delivery" for why this is deliberately not on the critical path.
   *
   * Bounded by DELIVER_TIMEOUT_MS so a hanging backend resolves false
   * instead of leaving the caller's promise pending forever.
   */
  async deliver(runId: number): Promise<{ delivered: boolean; detail?: string }> {
    try {
      const res = await firstValueFrom(
        this.http
          .post<{ run_id: number; delivered: boolean; detail?: string }>(
            `${API_BASE}/${runId}/deliver`,
            {},
            { headers: { Authorization: `Bearer ${APP_TOKEN}` } }
          )
          .pipe(timeout(DELIVER_TIMEOUT_MS))
      );
      // 200 with delivered:false is the normal case while Garuda is
      // unconfigured — the endpoint reports honestly instead of throwing.
      return { delivered: !!res?.delivered, detail: res?.detail };
    } catch {
      return { delivered: false, detail: 'delivery endpoint unreachable' };
    }
  }

  /**
   * POST /v1/analysis/runs/{id}/prd/{rank}/chat — chat-style PRD editing
   * (prd_editor.py). Recognises a handful of concrete instructions ("title:
   * ...", "remove FR-3"); anything else gets appended to the PRD as an
   * unresolved reviewer request and an honest reply saying so — there is no
   * LLM rewrite path wired up yet, so this never fabricates an edit it
   * didn't actually make.
   *
   * Only meaningful against a live run (the PRD has to exist as a
   * `RunArtifact` row/file on the backend); callers should gate this behind
   * `source() === 'live'`, same discipline as `deliver()`.
   *
   * On success, patches the local `prds[]` signal in place so the drawer
   * reflects the edit without a re-poll.
   */
  async chatOnPrd(
    runId: number,
    rank: number,
    message: string
  ): Promise<{ reply: string; markdown: string; applied: boolean } | { error: string }> {
    try {
      const res = await firstValueFrom(
        this.http
          .post<{ finding_rank: number; reply: string; markdown: string; applied: boolean }>(
            `${API_BASE}/${runId}/prd/${rank}/chat`,
            { message },
            { headers: { Authorization: `Bearer ${APP_TOKEN}` } }
          )
          .pipe(timeout(PRD_CHAT_TIMEOUT_MS))
      );
      this._run.update((run) => ({
        ...run,
        prds: run.prds.map((p): PrdSummary => (p.finding_rank === rank ? { ...p, markdown: res.markdown, edited: true } : p)),
      }));
      return { reply: res.reply, markdown: res.markdown, applied: res.applied };
    } catch (err) {
      if (err instanceof HttpErrorResponse) {
        if (err.status === 401) return { error: 'not authorised — check APP_TOKEN' };
        if (err.status === 404) return { error: 'no PRD found for this run/finding' };
        return { error: describeError(err) };
      }
      return { error: 'request timed out' };
    }
  }

  private failedStatuses(run: RunState): StageStatus[] {
    const reached = (run.code_gaps?.length ?? 0) ? 3 : (run.findings?.length ?? 0) ? 2 : (run.snapshot?.stages?.length ?? 0) ? 1 : 0;
    const statuses: StageStatus[] = ['done', 'done', 'done', 'done'];
    for (let i = reached; i < 4; i++) statuses[i] = i === reached ? 'failed' : 'pending';
    return statuses;
  }

  private summaryFor(key: StageKey, run: RunState, status: StageStatus): string {
    if (status === 'pending') return '—';
    if (status === 'failed') return 'failed';
    switch (key) {
      case 'fetch': {
        // Backend keys are total/negatives; older fixtures said pulled/negative.
        const meta = run.voc?.reviews_meta ?? {};
        const pulled = meta['total'] ?? meta['pulled'];
        const rows = run.snapshot?.stages?.length ?? 0;
        if (status === 'running' || !rows) return 'fetching the funnel…';
        return `${rows} stage rows · ${pulled ?? '—'} reviews`;
      }
      case 'analyze': {
        const findings = run.findings ?? [];
        return status === 'running'
          ? `drilling down… (query ${run.drilldown_trail?.length ?? 0}/10)`
          : `${findings.length} findings, ${findings.some((f) => f.rank === 1) ? 1 : 0} critical`;
      }
      case 'code': {
        const gaps = run.code_gaps ?? [];
        if (status === 'running') return 'searching the owning repos…';
        const found = gaps.filter((g) => g.mechanism_found);
        const remedies = found.reduce((n, g) => n + (g.remedies?.length ?? 0), 0);
        const suggestions = run.suggestions?.length ?? 0;
        if (!gaps.length && !suggestions) return 'no code gaps yet';
        const parts = [`${found.length} mechanism(s) pinned`, `${remedies} remedy verdict(s)`];
        if (suggestions) parts.push(`${suggestions} suggestion(s)`);
        return parts.join(' · ');
      }
      case 'prd':
        return run.prd_draft ? 'PRD draft ready' : 'PRD draft ready (built from findings)';
    }
  }
}
