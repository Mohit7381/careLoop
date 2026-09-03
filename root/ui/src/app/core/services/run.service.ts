import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { EMPTY, Subscription, timer } from 'rxjs';
import { catchError, switchMap, tap } from 'rxjs/operators';

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

export type Source = 'fixture' | 'live' | 'live-unreachable';

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
const API_BASE = '/v1/analysis/runs';

@Injectable({ providedIn: 'root' })
export class RunService {
  private readonly http = inject(HttpClient);

  private readonly _run = signal<RunState>(RUN_47);
  private readonly _source = signal<Source>('fixture');
  private readonly _polling = signal(false);
  private pollSub: Subscription | null = null;

  readonly run = this._run.asReadonly();
  readonly source = this._source.asReadonly();
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
    this._run.set(RUN_47);
    this._demoOverride.set(null);
    this._revealOverride.set(null);
    this._trailProgress.set(null);
  }

  /** Switches to polling GET /v1/analysis/runs/{id} every 1.5s until the
   *  run reaches completed|failed. Falls back to the fixture — and says so
   *  via `source` — on any fetch failure, so the screen is never left mid
   *  state on stage. */
  goLive(runId: number): void {
    this.stopPolling();
    this._source.set('live');
    this._polling.set(true);

    this.pollSub = timer(0, POLL_MS)
      .pipe(
        switchMap(() =>
          this.http.get<RunState>(`${API_BASE}/${runId}`).pipe(
            catchError(() => {
              this._source.set('live-unreachable');
              this._run.set(RUN_47);
              this.stopPolling();
              return EMPTY;
            })
          )
        ),
        tap((run) => {
          this._run.set(run);
          if (run.status === 'completed' || run.status === 'failed') {
            this.stopPolling();
          }
        })
      )
      .subscribe();
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
   */
  async deliver(runId: number, channel: string): Promise<boolean> {
    try {
      await this.http.post(`${API_BASE}/${runId}/deliver`, { channel }).toPromise();
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
