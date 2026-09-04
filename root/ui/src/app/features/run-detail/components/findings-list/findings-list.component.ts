import { Component, input } from '@angular/core';

import { VocPanelComponent } from '../voc-panel/voc-panel.component';
import { EvidenceItem, Finding, Voc } from '../../../../core/models/run-state';

const SEV_BY_RANK: Record<number, { label: string; tone: string }> = {
  1: { label: 'CRITICAL', tone: 'crit' },
  2: { label: 'HIGH', tone: 'high' },
  3: { label: 'MEDIUM', tone: 'med' },
};

@Component({
  selector: 'app-findings-list',
  imports: [VocPanelComponent],
  templateUrl: './findings-list.component.html',
  styleUrl: './findings-list.component.scss',
})
export class FindingsListComponent {
  readonly findings = input.required<Finding[]>();
  readonly voc = input.required<Voc>();

  /** Quotes are keyed by finding rank; only render the panel where there are
   *  actually quotes to show. */
  hasQuotes(rank: number): boolean {
    return (this.voc().per_finding_quotes?.[String(rank)]?.length ?? 0) > 0;
  }

  sorted(): Finding[] {
    return [...this.findings()].sort((a, b) => a.rank - b.rank);
  }

  /** USER-REPORTED findings are not shown as cards. */
  cards(): Finding[] {
    return this.sorted().filter((f) => f.origin !== 'voc');
  }

  /**
   * Their review quotes still are. per_finding_quotes is keyed to exactly
   * the VoC-origin ranks (4 and 5 on a typical run), so hiding those cards
   * without this would take the whole "Users say" panel with them.
   */
  quoteOnly(): Finding[] {
    return this.sorted().filter((f) => f.origin === 'voc' && this.hasQuotes(f.rank));
  }

  sevLabel(f: Finding): string {
    return f.origin === 'voc' ? 'USER-REPORTED' : (SEV_BY_RANK[f.rank]?.label ?? 'MEDIUM');
  }

  tone(f: Finding): string {
    return f.origin === 'voc' ? 'vocc' : (SEV_BY_RANK[f.rank]?.tone ?? 'med');
  }

  /** "routes to consultation" meant nothing to a product reader; say who owns it. */
  teamLabel(f: Finding): string {
    return `for the ${f.stage.replace(/_/g, ' ')} team`;
  }

  magnitude(f: Finding): string {
    if (f.origin === 'voc') {
      return `${f.review_count ?? 0} reviews on '${f.theme ?? '—'}'`;
    }
    const segs = (f.segments ?? []).map((s) => `${s.dimension.replace(/_/g, ' ')}: ${String(s.value).replace(/_/g, ' ')}`);
    return segs.join(' · ') || 'all users';
  }

  chips(f: Finding): string[] {
    if (f.origin === 'voc') {
      return [`${f.review_count ?? 0} reviews`, ...(f.theme_search_terms ?? []).slice(0, 3).map((t) => `code search: ${t}`)];
    }
    return (f.evidence ?? []).map((e) => this.chipText(e));
  }

  /** Prefer the backend's plain-words label; the raw row stays available as the
   *  chip's title for anyone who wants to audit the exact number. */
  private chipText(e: EvidenceItem): string {
    if (e.label && e.label !== e.metric) return e.label;
    const val = e.value % 1 === 0 ? e.value.toLocaleString('en-US') : e.value.toFixed(1);
    return `${e.metric}: ${val}`;
  }

  /** contracts.py sends a literal now ("high"/"medium"/"low"), not a float. */
  confLabel(f: Finding): string {
    return (f.confidence ?? 'medium').toUpperCase();
  }
}
