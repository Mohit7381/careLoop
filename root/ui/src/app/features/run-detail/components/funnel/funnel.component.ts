import { Component, computed, input } from '@angular/core';

import { Finding, Snapshot } from '../../../../core/models/run-state';

interface FunnelRow {
  label: string;
  value: number;
  pct: number;
  terminal: boolean;
}

interface FunnelGroup {
  unit: string;
  rows: FunnelRow[];
}

interface FunnelNote {
  tag: string;
  text: string;
}

/**
 * The funnel mixes two units in one visual: rows 0-2 of
 * Snapshot.stages are unique users (app events), rows 3-5 are orders
 * (backend) — see run-47.fixture.ts. Scaling them on one shared axis
 * would draw a collapse that never happened (77,482 users -> 643,626
 * orders is a UNIT change, not a drop). Each group gets its own max and
 * its own bar color, with the unit named above it.
 */
@Component({
  selector: 'app-funnel',
  templateUrl: './funnel.component.html',
  styleUrl: './funnel.component.scss',
})
export class FunnelComponent {
  readonly snapshot = input.required<Snapshot>();
  /** Ranks 1-2 drive the red leak annotations under the funnel — pulled
   *  from Finding.evidence[] rather than a separate "notes" field, because
   *  contracts.py has no such field: the annotation IS the finding. */
  readonly findings = input<Finding[]>([]);

  readonly notes = computed<FunnelNote[]>(() => {
    const out: FunnelNote[] = [];
    const f1 = this.findings().find((f) => f.rank === 1);
    const f2 = this.findings().find((f) => f.rank === 2);
    if (f1) {
      const abandoned = f1.evidence?.find((e) => e.metric === 'abandoned')?.value;
      out.push({
        tag: 'ABANDON',
        text: abandoned != null ? `${abandoned.toLocaleString('en-US')} orders abandoned` : f1.hypothesis,
      });
    }
    if (f2) {
      const gated = f2.evidence?.find((e) => e.metric === 'rx_gated_abandons_per_week')?.value;
      out.push({
        tag: 'RX-GATED',
        text: gated != null ? `Prescription-gated carts drive ~${gated.toLocaleString('en-US')}/week of that` : f2.hypothesis,
      });
    }
    return out;
  });

  readonly groups = computed<FunnelGroup[]>(() => {
    const rows = this.snapshot().stages;
    if (rows.length < 6) {
      return [{ unit: 'orders · backend', rows: this.toRows(rows) }];
    }
    return [
      { unit: 'unique users · app events', rows: this.toRows(rows.slice(0, 3)) },
      { unit: 'orders · backend', rows: this.toRows(rows.slice(3, 6)) },
    ];
  });

  private toRows(rows: Snapshot['stages']): FunnelRow[] {
    const max = Math.max(...rows.map((r) => r.entered), 1);
    return rows.map((r, i) => ({
      label: r.stage,
      value: r.entered,
      pct: +((r.entered / max) * 100).toFixed(1),
      terminal: i === rows.length - 1,
    }));
  }

  barWidth(row: FunnelRow, group: FunnelGroup): number {
    const max = Math.max(...group.rows.map((r) => r.value), 1);
    return (row.value / max) * 100;
  }
}
