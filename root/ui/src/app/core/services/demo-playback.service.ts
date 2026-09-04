import { Injectable, inject } from '@angular/core';

import { RunService, StageStatus, StageView } from './run.service';

const LABELS: Record<'fetch' | 'analyze' | 'code' | 'prd', string> = {
  fetch: 'FETCH DATA',
  analyze: 'ANALYZE DROP-OFFS',
  code: 'SCAN SERVICE CODE',
  prd: 'DRAFT SUGGESTIONS',
};

/**
 * Drives the "Replay run" demo animation in fixture mode: hard-coded timer
 * beats, not real backend progress, so every rehearsal runs identically.
 * This is a deliberate choice — see RunService's STATUS_MAP doc comment for
 * why the live path cannot express this level of per-stage timing today.
 *
 * Ported from the original HTML prototype's playDemo() beat schedule.
 */
@Injectable({ providedIn: 'root' })
export class DemoPlaybackService {
  private readonly runService = inject(RunService);
  private timers: ReturnType<typeof setTimeout>[] = [];

  get reducedMotion(): boolean {
    return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  }

  play(): void {
    this.clear();
    if (this.reducedMotion) {
      this.settleComplete();
      return;
    }

    const trailLen = this.runService.run().drilldown_trail.length;
    const beat = (ms: number, statuses: StageStatus[], summaries: Partial<Record<'fetch' | 'analyze' | 'code' | 'prd', string>>) =>
      this.at(ms, () => this.apply(statuses, summaries));

    const P: StageStatus = 'pending';
    const R: StageStatus = 'running';
    const D: StageStatus = 'done';

    beat(0, [P, P, P, P], {});
    beat(200, [R, P, P, P], { fetch: 'querying Metabase…' });
    beat(1500, [D, R, P, P], { analyze: 'clustering reasons…' });
    this.at(1500, () => this.runService.setReveal({ funnel: true, findings: false, code: false }));
    this.at(1500, () => this.runService.setTrailProgress(0));

    for (let i = 1; i <= trailLen; i++) {
      this.at(2600 + i * 900, () => {
        this.runService.setTrailProgress(i);
        this.apply([D, R, P, P], { analyze: `drilling down… (query ${i}/10)` });
      });
    }

    const tEnd = 2600 + trailLen * 900 + 900;
    this.at(tEnd - 300, () => this.runService.setReveal({ funnel: true, findings: true, code: false }));
    beat(tEnd, [D, D, R, P], { code: 'searching bintan/consultation…' });
    this.at(tEnd, () => this.runService.setReveal({ funnel: true, findings: true, code: false }));
    beat(tEnd + 2200, [D, D, D, R], { prd: 'drafting…' });
    this.at(tEnd + 2200, () => this.runService.setReveal({ funnel: true, findings: true, code: true }));
    this.at(tEnd + 3600, () => this.settleComplete());
  }

  private settleComplete(): void {
    this.clear();
    this.runService.setReveal(null);
    this.runService.setTrailProgress(null);
    this.runService.setStageOverride(null);
  }

  private apply(statuses: StageStatus[], summaries: Partial<Record<'fetch' | 'analyze' | 'code' | 'prd', string>>): void {
    const keys: ('fetch' | 'analyze' | 'code' | 'prd')[] = ['fetch', 'analyze', 'code', 'prd'];
    const run = this.runService.run();
    const view: StageView[] = keys.map((key, i) => ({
      key,
      label: LABELS[key],
      status: statuses[i],
      summary:
        statuses[i] === 'running'
          ? summaries[key] ?? 'working…'
          : statuses[i] === 'done'
            ? this.doneSummary(key, run)
            : '—',
    }));
    this.runService.setStageOverride(view);
  }

  private doneSummary(key: 'fetch' | 'analyze' | 'code' | 'prd', run: ReturnType<RunService['run']>): string {
    switch (key) {
      case 'fetch':
        return `${run.snapshot.stages.length} stage rows · ${run.voc.reviews_meta['pulled'] ?? 0} reviews`;
      case 'analyze':
        return `${run.findings.length} findings, 1 critical`;
      case 'code':
        return `${run.code_gaps.filter((g) => g.mechanism_found).length} mechanism(s) pinned`;
      case 'prd':
        return 'suggestions ready';
    }
  }

  private at(ms: number, fn: () => void): void {
    this.timers.push(setTimeout(fn, ms));
  }

  private clear(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
}
