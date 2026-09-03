import { Component, computed, input } from '@angular/core';

import { DrilldownStep } from '../../../../core/models/run-state';

@Component({
  selector: 'app-drilldown-trail',
  templateUrl: './drilldown-trail.component.html',
  styleUrl: './drilldown-trail.component.scss',
})
export class DrilldownTrailComponent {
  readonly rows = input.required<DrilldownStep[]>();
  /** How many rows are revealed right now (demo playback) — defaults to
   *  all, so the panel always shows complete at rest. */
  readonly visibleCount = input<number>(Infinity);
  readonly budget = input(10);

  readonly used = computed(() => Math.min(this.visibleCount(), this.rows().length));

  isConclusion(row: DrilldownStep): boolean {
    return row.dimension === 'conclusion';
  }

  isHit(row: DrilldownStep, index: number): boolean {
    // The "hit" row is the one right before the conclusion — matches the
    // fixture's authored order (see run-47.fixture.ts drilldown_trail).
    return !this.isConclusion(row) && index === this.rows().length - 2;
  }
}
