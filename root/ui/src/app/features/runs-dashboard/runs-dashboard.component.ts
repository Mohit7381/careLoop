import { Component, inject } from '@angular/core';
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

  newAnalysis(): void {
    // POST /v1/analysis/runs is async, 409-on-duplicate-window per the plan.
    // Not implemented yet on the backend — see README "Known gaps". Route
    // straight to the fixture run so the demo path always works.
    this.runService.loadFixture();
    this.router.navigate(['/runs', 47]);
  }
}
