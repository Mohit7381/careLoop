import { Component, computed, input } from '@angular/core';

import { glossFor } from '../../../../core/data/voc-gloss';
import { Voc, VocQuote } from '../../../../core/models/run-state';

interface QuoteView extends VocQuote {
  gloss: string | null;
}

@Component({
  selector: 'app-voc-panel',
  templateUrl: './voc-panel.component.html',
  styleUrl: './voc-panel.component.scss',
})
export class VocPanelComponent {
  readonly voc = input.required<Voc>();
  /** Which finding's quotes to show. The design prompt pinned this to #1, but
   *  the backend keys per_finding_quotes by the VoC-ORIGIN finding's rank
   *  (4 and 5 on a real run), so a hardcoded 1 rendered an empty panel on
   *  every live run. Now passed from the finding it sits under. */
  readonly findingRank = input.required<number>();
  /** The theme this finding escalated on — drives the source line, instead of
   *  the previously hardcoded 'payment/refund'. */
  readonly theme = input<string | null>(null);

  readonly quotes = computed<QuoteView[]>(() => {
    const raw = this.voc().per_finding_quotes[String(this.findingRank())] ?? [];
    return raw.map((q) => ({ ...q, gloss: glossFor(q.text) }));
  });

  readonly hasQuotes = computed(() => this.quotes().length > 0);

  stars(n: number): string {
    return '★'.repeat(Math.max(0, Math.min(5, n)));
  }
}
