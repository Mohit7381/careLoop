import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { DemoPlaybackService } from '../../core/services/demo-playback.service';
import { RunService } from '../../core/services/run.service';
import { CodeScoutPanelComponent } from './components/code-scout-panel/code-scout-panel.component';
import { SuggestionsPanelComponent } from './components/suggestions-panel/suggestions-panel.component';
import { FindingsListComponent } from './components/findings-list/findings-list.component';
import { FunnelComponent } from './components/funnel/funnel.component';
import { PipelineTrackerComponent } from './components/pipeline-tracker/pipeline-tracker.component';
import { PrdDrawerComponent } from './components/prd-drawer/prd-drawer.component';

/**
 * Screen 2 — Run detail. The demo's main screen: every beat in the 5-minute
 * script (pipeline tracker → funnel → findings → drill-down trail →
 * "Users say" → code scout → PRD) renders here.
 *
 * Loads at rest (fixture, everything visible) so a stage failure never
 * leaves the screen empty — press "Replay run" for the timed animation.
 */
@Component({
  selector: 'app-run-detail',
  imports: [RouterLink, PipelineTrackerComponent, FunnelComponent, FindingsListComponent, CodeScoutPanelComponent, SuggestionsPanelComponent, PrdDrawerComponent],
  templateUrl: './run-detail.component.html',
  styleUrl: './run-detail.component.scss',
})
export class RunDetailComponent {
  private readonly route = inject(ActivatedRoute);
  protected readonly runService = inject(RunService);
  private readonly playback = inject(DemoPlaybackService);

  readonly prdOpen = signal(false);

  readonly run = this.runService.run;
  readonly stages = this.runService.stages;
  readonly reveal = this.runService.reveal;
  readonly trailVisibleCount = this.runService.trailVisibleCount;
  readonly source = this.runService.source;
  readonly liveError = this.runService.liveError;


  /** True while the backend is still working on this run. */
  readonly inFlight = computed(() => !['completed', 'failed'].includes(this.run().status));

  /** Tone drives the pill colour; label shows the real backend stage. */
  readonly statusPill = computed(() => {
    const failed = this.stages().some((s) => s.status === 'failed');
    const allDone = this.stages().every((s) => s.status === 'done');
    return failed ? 'failed' : allDone ? 'completed' : 'analyzing';
  });
  readonly statusLabel = computed(() =>
    this.inFlight() ? this.run().status.replace(/_/g, ' ') : this.statusPill()
  );

  /** Journey name from the API, humanised; pharmacy is the historical default. */
  readonly journeyLabel = computed(() => {
    const j = (this.run() as unknown as { journey?: string }).journey ?? 'pd_checkout';
    return j === 'pd_checkout' ? 'pharmacy delivery order journey' : `${j.replace(/_/g, ' ')} journey`;
  });

  readonly hasFunnel = computed(() => (this.run().snapshot?.stages?.length ?? 0) > 0);
  readonly hasFindings = computed(() => (this.run().findings?.length ?? 0) > 0);
  readonly hasCode = computed(() => (this.run().code_gaps?.length ?? 0) > 0);

  readonly prdReady = computed(() => this.stages().every((s) => s.status === 'done'));

  constructor() {
    const idParam = this.route.snapshot.paramMap.get('id');
    // Number('abc') is NaN, which used to be interpolated straight into the
    // URL as GET /v1/analysis/runs/NaN. Fall back to the fixture id instead.
    const parsed = idParam !== null ? Number(idParam) : NaN;
    const id = Number.isInteger(parsed) && parsed > 0 ? parsed : 47;
    // Fixture-only for now: the /deliver and live-polling paths are wired
    // in RunService and exercised via ?live=<id>, but no backend serves
    // GET /v1/analysis/runs/{id} yet outside impl/codeScout's tests. See
    // README "Running against the real backend".
    if (this.route.snapshot.queryParamMap.get('live')) {
      this.runService.goLive(id);
    } else {
      this.runService.loadFixture();
    }
  }

  replay(): void {
    this.playback.play();
  }

  openPrd(): void {
    this.prdOpen.set(true);
  }
  closePrd(): void {
    this.prdOpen.set(false);
  }

  @HostListener('window:keydown', ['$event'])
  onKeydown(e: KeyboardEvent): void {
    const target = e.target as HTMLElement | null;
    if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
    // R/P are gone with their badges — a bare letter key that fires a CTA is
    // a trap once the page has more than a couple of controls. Escape stays:
    // closing an open drawer is what it is for.
    if (e.key === 'Escape') {
      this.closePrd();
    }
  }
}
