import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { EMPTY, Subscription, firstValueFrom, timer } from 'rxjs';
import { catchError, switchMap, tap, timeout } from 'rxjs/operators';

import { RUN_47 } from '../fixtures/run-47.fixture';
import { RunState, RunStatus } from '../models/run-state';

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
  extracting: ['running', 'pending', 'pending', 'pending'],
  analyzing: ['done', 'running', 'pending', 'pending'],
  reporting: ['done', 'done', 'done', 'running'],
  completed: ['done', 'done', 'done', 'done'],
};

const STAGE_KEYS: StageKey[] = ['fetch', 'analyze', 'code', 'prd'];
const POLL_MS = 1500;
const REQUEST_TIMEOUT_MS = 10_000;
const DELIVER_TIMEOUT_MS = 8_000;
const MAX_RETRIES = 2;
const API_BASE = '/v1/analysis/runs';

/**
 * Runtime shape check on the polled payload.
 *
 * `http.get<RunState>()` is a compile-time assertion, not a guarantee —
 * the server can send anything. This matters concretely here: Code Scout
 * moved from `code_gaps` (Rev 2) to `suggestions` (Rev 3) mid-build, and a
 * backend still on Rev 2 sends a body with no `suggestions` key at all.
 * Without this check the computed stage summary throws on
 * `suggestions.length`, Angular keeps the last good value, and the screen
 * renders the LIVE run's header over the FIXTURE's funnel, findings and
 * counts — every number belonging to a different run than the header
 * claims, with the source chip still reading "live". Fail loudly instead.
 *
 * Deliberately shallow: it checks the fields this UI dereferences, not the
 * whole contract. A schema validator (zod) would be the real answer if the
 * contract keeps moving.
 */
function validateRunState(body: unknown): { ok: true; run: RunState } | { ok: false; reason: string } {
  if (!body || typeof body !== 'object') return { ok: false, reason: 'response was not an object' };
  const r = body as Partial<RunState>;

  if (typeof r.run_id !== 'number') return { ok: false, reason: 'missing run_id' };
  if (typeof r.status !== 'string') return { ok: false, reason: 'missing status' };
  if (!Array.isArray(r.findings)) return { ok: false, reason: 'missing findings[]' };
  if (!Array.isArray(r.drilldown_trail)) return { ok: false, reason: 'missing drilldown_trail[]' };
  if (!Array.isArray(r.suggestions)) {
    return {
      ok: false,
      // Named explicitly: this is the Rev 2 -> Rev 3 skew, the single most
      // likely reason a real backend fails this check today.
      reason: Array.isArray((r as { code_gaps?: unknown[] }).code_gaps)
        ? 'backend is on the Rev 2 contract (code_gaps, no suggestions[])'
        : 'missing suggestions[]',
    };
  }
  if (!r.snapshot || !Array.isArray(r.snapshot.stages)) return { ok: false, reason: 'missing snapshot.stages[]' };
  if (!r.voc || typeof r.voc !== 'object') return { ok: false, reason: 'missing voc' };

  return { ok: true, run: body as RunState };
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

  private readonly _run = signal<RunState>(RUN_47);
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
    this._run.set(RUN_47);
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
          const result = validateRunState(body);
          if (!result.ok) {
            // A malformed payload is not transient — no point retrying it.
            this.failLive(result.reason);
            return;
          }
          consecutiveFailures = 0;
          this._run.set(result.run);
          if (result.run.status === 'completed' || result.run.status === 'failed') {
            this.stopPolling();
          }
        })
      )
      .subscribe();
  }

  /** Abandon the live source, say why, and show the fixture — never a mix. */
  private failLive(reason: string): void {
    this._source.set('live-failed');
    this._liveError.set(reason);
    this._run.set(RUN_47);
    this.stopPolling();
  }

  stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
    this._polling.set(false);
  }

  /**
   * POST /v1/analysis/runs/{id}/deliver — NOT YET IMPLEMENTED on the
   * backend (not in the API table in the PRD). Optimistic by design: the
   * caller shows its own success state immediately and calls this in the
   * background, so a slow or dead Garuda/GChat integration can never
   * produce a dead moment on stage. See README "Known gaps — GChat
   * delivery" for why this is deliberately not on the critical path.
   *
   * Bounded by DELIVER_TIMEOUT_MS so a hanging backend resolves false
   * instead of leaving the caller's promise pending forever.
   */
  async deliver(runId: number, channel: string): Promise<boolean> {
    try {
      await firstValueFrom(
        this.http.post(`${API_BASE}/${runId}/deliver`, { channel }).pipe(timeout(DELIVER_TIMEOUT_MS))
      );
      return true;
    } catch {
      return false;
    }
  }

  private failedStatuses(run: RunState): StageStatus[] {
    const reached = run.suggestions.length ? 3 : run.findings.length ? 2 : run.snapshot.stages.length ? 1 : 0;
    const statuses: StageStatus[] = ['done', 'done', 'done', 'done'];
    for (let i = reached; i < 4; i++) statuses[i] = i === reached ? 'failed' : 'pending';
    return statuses;
  }

  private summaryFor(key: StageKey, run: RunState, status: StageStatus): string {
    if (status === 'pending') return '—';
    if (status === 'failed') return 'failed';
    switch (key) {
      case 'fetch':
        return `${run.snapshot.stages.length} stage rows · ${run.voc.reviews_meta['pulled'] ?? 0} reviews`;
      case 'analyze':
        return status === 'running'
          ? `drilling down… (query ${run.drilldown_trail.length}/10)`
          : `${run.findings.length} findings, ${run.findings.filter((f) => f.rank === 1).length ? 1 : 0} critical`;
      case 'code': {
        const n = run.suggestions.length;
        const findings = new Set(run.suggestions.map((sg) => sg.finding_rank)).size;
        return n ? `${n} suggestion(s) across ${findings} finding(s)` : 'no suggestions yet';
      }
      case 'prd':
        return run.prd_draft ? 'PRD draft ready' : 'PRD draft ready (built from findings)';
    }
  }
}
