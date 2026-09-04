import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ResolvedScope, RunService, RunSummary } from '../../core/services/run.service';

interface RunRow {
  id: number;
  journey: string;
  prompt: string | null;
  scopeSummary: string;
  window: string;
  status: 'queued' | 'analyzing' | 'completed' | 'failed';
  topFinding: string;
  findingsCount: number;
  timestamp: string;
}

const POLL_MS = 1500;
const IN_FLIGHT = new Set(['queued', 'fetching', 'analyzing', 'scanning_code', 'reporting', 'drafting_prd']);

/**
 * Screen 1 — ask a question, get a run.
 *
 * The table loads real run history from GET /runs on open (newest first) —
 * every run is already sitting in analysis_runs regardless of which tab or
 * session created it, so a reload or a fresh tab must show the same history,
 * not an empty table until you ask something new. A row still only ever
 * reads as a fact: history rows come straight from the backend the same as
 * a freshly-created one does, never a client-side fixture.
 *
 * Submitting resolves the prompt first and shows the reading back before
 * anything runs. Scope resolution is deterministic and cheap, so confirming
 * costs nothing, and a misreading is caught before it becomes a finished
 * report answering the wrong question.
 */
@Component({
  selector: 'app-runs-dashboard',
  imports: [FormsModule],
  templateUrl: './runs-dashboard.component.html',
  styleUrl: './runs-dashboard.component.scss',
})
export class RunsDashboardComponent implements OnInit {
  private readonly runService = inject(RunService);
  private readonly router = inject(Router);

  readonly prompt = signal('');
  readonly resolving = signal(false);
  readonly creating = signal(false);
  readonly loadingHistory = signal(true);
  readonly preview = signal<ResolvedScope | null>(null);
  readonly error = signal<string | null>(null);
  readonly rows = signal<RunRow[]>([]);

  readonly hasRows = computed(() => this.rows().length > 0);
  readonly canSubmit = computed(
    () => !this.resolving() && !this.creating() && this.prompt().trim().length > 0
  );

  readonly examples = [
    'why are users dropping off after adding items to cart',
    'check how many and why the users are dropping off during the payments',
    'why do orders with unfulfilled items fail, last 10-15 days of reviews',
    'why do consultations get abandoned before the doctor joins',
  ];

  async ngOnInit(): Promise<void> {
    const summaries = await this.runService.listRuns();
    this.loadingHistory.set(false);
    if (!summaries.length) return;

    this.rows.set(summaries.map((s) => this.toRow(s)));
    for (const s of summaries) {
      if (IN_FLIGHT.has(s.status)) this.track(s.run_id);
    }
  }

  private toRow(s: RunSummary): RunRow {
    const status = (IN_FLIGHT.has(s.status) ? 'analyzing' : s.status) as RunRow['status'];
    return {
      id: s.run_id,
      journey: s.journey,
      prompt: s.prompt ?? null,
      scopeSummary: s.scope_summary ?? '',
      window: `${s.window_start} → ${s.window_end}`,
      status,
      topFinding: s.top_finding ?? (status === 'analyzing' ? 'Analysing…' : '—'),
      findingsCount: s.findings_count,
      timestamp: s.created_at.slice(0, 16).replace('T', ' '),
    };
  }

  useExample(text: string): void {
    this.prompt.set(text);
    this.preview.set(null);
    this.error.set(null);
  }

  /** Step 1 — show what the question was understood to mean. Runs nothing. */
  async resolve(): Promise<void> {
    if (!this.canSubmit()) return;
    this.resolving.set(true);
    this.error.set(null);
    this.preview.set(null);

    const res = await this.runService.resolveScope(this.prompt().trim());
    this.resolving.set(false);

    if ('error' in res) {
      this.error.set(`Could not reach CareLoop (${res.error}).`);
      return;
    }
    this.preview.set(res);
  }

  editQuestion(): void {
    this.preview.set(null);
  }

  /** Step 2 — the reading was accepted, so spend a run on it. */
  async run(): Promise<void> {
    if (this.creating()) return;
    this.creating.set(true);
    this.error.set(null);

    const asked = this.prompt().trim();
    const summary = this.preview()?.summary ?? '';
    const res = await this.runService.createRun('auto', asked || undefined);
    this.creating.set(false);

    if ('error' in res) {
      this.error.set(`Could not start the run: ${res.error}`);
      return;
    }

    this.rows.update((rows) => [
      {
        id: res.runId,
        journey: res.journey ?? this.preview()?.journey ?? 'pd_checkout',
        prompt: asked || null,
        scopeSummary: res.scopeSummary ?? summary,
        window: '—',
        status: 'analyzing',
        topFinding: 'Analysing…',
        findingsCount: 0,
        timestamp: new Date().toISOString().slice(0, 16).replace('T', ' '),
      },
      ...rows.filter((r) => r.id !== res.runId),
    ]);

    this.preview.set(null);
    this.prompt.set('');
    this.track(res.runId);
  }

  /**
   * Polls until the run settles, so the row fills in where the user is looking
   * rather than only on the detail page. Stops on any terminal state — a failed
   * run has to stay visible and say so, not disappear.
   */
  private track(runId: number): void {
    const tick = async () => {
      const run = await this.runService.fetchRun(runId);
      if (!run) {
        window.setTimeout(tick, POLL_MS);
        return;
      }
      const warehouse = (run.findings ?? []).filter((f) => f.origin === 'warehouse');
      const top = [...(run.findings ?? [])].sort((a, b) => a.rank - b.rank)[0];
      this.rows.update((rows) =>
        rows.map((r) =>
          r.id !== runId
            ? r
            : {
                ...r,
                status: (IN_FLIGHT.has(run.status) ? 'analyzing' : run.status) as RunRow['status'],
                window: `${run.window_start} → ${run.window_end}`,
                findingsCount: run.findings?.length ?? 0,
                topFinding:
                  run.status === 'failed'
                    ? `Failed at ${run.failed_stage ?? 'an unknown stage'}`
                    : top?.hypothesis ?? (warehouse.length ? '—' : 'Analysing…'),
              }
        )
      );
      if (IN_FLIGHT.has(run.status)) window.setTimeout(tick, POLL_MS);
    };
    window.setTimeout(tick, POLL_MS);
  }

  open(row: RunRow): void {
    if (row.status === 'queued') return;
    this.router.navigate(['/runs', row.id], { queryParams: { live: 1 } });
  }
}
