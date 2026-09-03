import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { EXPLORED_ANCHORS } from '../../core/fixtures/run-47.fixture';
import { DemoPlaybackService } from '../../core/services/demo-playback.service';
import { RunService } from '../../core/services/run.service';
import { CodeScoutPanelComponent } from './components/code-scout-panel/code-scout-panel.component';
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
  imports: [RouterLink, PipelineTrackerComponent, FunnelComponent, FindingsListComponent, CodeScoutPanelComponent, PrdDrawerComponent],
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

  /** Fixture-only enrichment for the Code Scout panel's code snippets —
   *  see CodeScoutPanelComponent's doc comment. Not present on a live
   *  RunState (contracts.py's Suggestion has no snippet field), so a live
   *  run shows verification chips + file:line only, no code block, until
   *  that's resolved with Harshit. */
  readonly anchors = EXPLORED_ANCHORS;

  readonly statusPill = computed(() => {
    const failed = this.stages().some((s) => s.status === 'failed');
    const allDone = this.stages().every((s) => s.status === 'done');
    return failed ? 'failed' : allDone ? 'completed' : 'analyzing';
  });

  readonly prdReady = computed(() => this.stages().every((s) => s.status === 'done'));

  constructor() {
    const idParam = this.route.snapshot.paramMap.get('id');
    const id = idParam ? Number(idParam) : 47;
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
    const key = e.key.toLowerCase();
    if (key === 'r') {
      e.preventDefault();
      this.replay();
    } else if (key === 'p') {
      e.preventDefault();
      this.openPrd();
    } else if (e.key === 'Escape') {
      this.closePrd();
    }
  }
}
