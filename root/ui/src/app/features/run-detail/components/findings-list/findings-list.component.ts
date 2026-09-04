import { Component, input } from '@angular/core';

import { DrilldownTrailComponent } from '../drilldown-trail/drilldown-trail.component';
import { VocPanelComponent } from '../voc-panel/voc-panel.component';
import { DrilldownStep, EvidenceItem, Finding, Voc } from '../../../../core/models/run-state';

const SEV_BY_RANK: Record<number, { label: string; tone: string }> = {
  1: { label: 'CRITICAL', tone: 'crit' },
  2: { label: 'HIGH', tone: 'high' },
  3: { label: 'MEDIUM', tone: 'med' },
};

@Component({
  selector: 'app-findings-list',
  imports: [DrilldownTrailComponent, VocPanelComponent],
  templateUrl: './findings-list.component.html',
  styleUrl: './findings-list.component.scss',
})
export class FindingsListComponent {
  readonly findings = input.required<Finding[]>();
  readonly drilldownTrail = input.required<DrilldownStep[]>();
  readonly trailVisibleCount = input<number>(Infinity);
  readonly voc = input.required<Voc>();

  /** Quotes are keyed by finding rank; only render the panel where there are
   *  actually quotes to show. */
  hasQuotes(rank: number): boolean {
    return (this.voc().per_finding_quotes?.[String(rank)]?.length ?? 0) > 0;
  }

  /** The drill-down trail describes the warehouse analysis, so it hangs off
   *  the top warehouse finding — which is not always rank 1. */
  topWarehouseRank(): number {
    const w = this.findings().filter((f) => f.origin === 'warehouse').sort((a, b) => a.rank - b.rank);
    return w[0]?.rank ?? this.sorted()[0]?.rank ?? 1;
  }

  sorted(): Finding[] {
    return [...this.findings()].sort((a, b) => a.rank - b.rank);
  }

  sevLabel(f: Finding): string {
    return f.origin === 'voc' ? 'USER-REPORTED' : (SEV_BY_RANK[f.rank]?.label ?? 'MEDIUM');
  }

  tone(f: Finding): string {
    return f.origin === 'voc' ? 'vocc' : (SEV_BY_RANK[f.rank]?.tone ?? 'med');
  }

  magnitude(f: Finding): string {
    if (f.origin === 'voc') {
      return `${f.review_count ?? 0} reviews · theme: ${f.theme ?? '—'} · routed to Code Scout`;
    }
    return (f.segments ?? []).map((s) => `${s.dimension}=${s.value}`).join(' · ') || 'all users';
  }

  chips(f: Finding): string[] {
    if (f.origin === 'voc') {
      return [`review_count: ${f.review_count ?? 0}`, ...(f.theme_search_terms ?? []).slice(0, 3).map((t) => `term: ${t}`)];
    }
    return (f.evidence ?? []).map((e) => this.chipText(e));
  }

  private chipText(e: EvidenceItem): string {
    const val = e.value % 1 === 0 ? e.value.toLocaleString('en-US') : e.value.toFixed(1);
    return `${e.metric}: ${val}`;
  }

  /** contracts.py sends a literal now ("high"/"medium"/"low"), not a float. */
  confLabel(f: Finding): string {
    return (f.confidence ?? 'medium').toUpperCase();
  }
}
