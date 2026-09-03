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
  /** Which finding rank's quotes to show — "Users say" is attached beneath
   *  finding #1 in the design prompt. */
  readonly findingRank = input(1);

  readonly quotes = computed<QuoteView[]>(() => {
    const raw = this.voc().per_finding_quotes[String(this.findingRank())] ?? [];
    return raw.map((q) => ({ ...q, gloss: glossFor(q.text) }));
  });

  readonly sourceLine = computed(() => {
    const meta = this.voc().reviews_meta;
    const theme = this.voc().themes.find((t) => t['name'] === 'payment/refund');
    const negs = theme ? `${theme['negatives']}` : '?';
    return `${meta['pulled'] ?? '?'} newest reviews · ${meta['negative'] ?? '?'} negative · theme: payment/refund (${negs})`;
  });

  stars(n: number): string {
    return '★'.repeat(Math.max(0, Math.min(5, n)));
  }
}
