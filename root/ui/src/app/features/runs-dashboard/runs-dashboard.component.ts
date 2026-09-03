import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { RunService } from '../../core/services/run.service';

interface RunRow {
  id: number;
  window: string;
  status: 'completed' | 'analyzing' | 'failed';
  topFinding: string;
  findingsCount: number;
  timestamp: string;
}

/**
 * Screen 1 — Runs dashboard (home). Minimal on purpose: the design prompt
 * gives it five seconds of screen time and none of the demo script's
 * beats happen here — everything real lives on Screen 2 (RunDetail). A
 * static past-runs table plus "New analysis" is enough.
 */
@Component({
  selector: 'app-runs-dashboard',
  templateUrl: './runs-dashboard.component.html',
  styleUrl: './runs-dashboard.component.scss',
})
export class RunsDashboardComponent {
  private readonly runService = inject(RunService);
  private readonly router = inject(Router);

  readonly rows: RunRow[] = [
    {
      id: 47,
      window: '2026-08-26 → 2026-09-02',
      status: 'completed',
      topFinding: 'Orders die on a silent abandonment timer (413,973 abandoned/wk)',
      findingsCount: 4,
      timestamp: '2026-09-02 09:18',
    },
  ];

  open(id: number): void {
    this.router.navigate(['/runs', id]);
  }

  readonly creating = signal(false);
  readonly createError = signal<string | null>(null);

  /**
   * Creates a real run via POST /v1/analysis/runs and opens it in live mode.
   *
   * On 409 the backend returns the in-progress run's id, so a double-click
   * attaches to that run rather than erroring. If the backend is unreachable
   * we say so and fall back to the fixture, so the demo path still works —
   * but we never pretend a fixture is a fresh run.
   */
  async newAnalysis(): Promise<void> {
    if (this.creating()) return;
    this.creating.set(true);
    this.createError.set(null);

    const res = await this.runService.createRun();
    this.creating.set(false);

    if ('error' in res) {
      this.createError.set(`${res.error} — showing the frozen fixture instead`);
      this.runService.loadFixture();
      this.router.navigate(['/runs', 47]);
      return;
    }
    // ?live=1 puts RunDetail on the polling path; the run starts as `queued`
    // and the stage tracker follows it through to completed.
    this.router.navigate(['/runs', res.runId], { queryParams: { live: 1 } });
  }
}
