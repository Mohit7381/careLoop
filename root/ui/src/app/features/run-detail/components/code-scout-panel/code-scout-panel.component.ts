import { Component, computed, input } from '@angular/core';

import { CodeGap } from '../../../../core/models/run-state';

const NO_MATCH_COPY: Record<string, string> = {
  no_results: 'No candidate mechanism matched the search terms.',
  budget_exhausted: 'Search budget spent before a mechanism was isolated.',
  ambiguous: 'Several candidate mechanisms matched; none conclusive.',
};

interface CodeToken {
  text: string;
  cls: 'kw' | 'str' | 'var' | 'plain';
}

/**
 * Renders CodeGap[] from Agent 3 (Code Scout) — the "money moment" panel.
 * mechanism_found=false is a first-class, contract-enforced outcome (see
 * CodeGap.model_post_init in contracts.py), not an error state: it gets
 * its own honest rendering, never an empty/broken card.
 */
@Component({
  selector: 'app-code-scout-panel',
  templateUrl: './code-scout-panel.component.html',
  styleUrl: './code-scout-panel.component.scss',
})
export class CodeScoutPanelComponent {
  readonly gaps = input.required<CodeGap[]>();

  readonly primary = computed<CodeGap | undefined>(() => this.gaps()[0]);

  noMatchCopy(gap: CodeGap): string {
    return (gap.no_match_reason && NO_MATCH_COPY[gap.no_match_reason]) || 'Not determined.';
  }

  gapClassLabel(gap: CodeGap): string {
    return gap.gap_class ? gap.gap_class.replace(/_/g, ' ').toUpperCase() : 'NO MECHANISM FOUND';
  }

  gapClassTone(gap: CodeGap): string {
    if (!gap.mechanism_found) return 'none';
    if (gap.gap_class === 'logic_flaw') return 'logic';
    if (gap.gap_class === 'ux_gap') return 'ux';
    return '';
  }

  /** Every fixture code_gap carries its own confidence/caveat text baked
   *  into gap_statement (see run-47.fixture.ts) rather than a separate
   *  contract field — surfaced verbatim, never smoothed over. */
  tokenize(snippet: string | null | undefined): CodeToken[] {
    if (!snippet) return [];
    const KEYWORDS = /\b(private|final|String|public|Order|Override|SELECT|FROM|WHERE|AND|IN|INTERVAL|MINUTE|now)\b/;
    return snippet.split(/(\s+|\b)/).filter(Boolean).map((tok) => {
      if (/^'[^']*'$/.test(tok)) return { text: tok, cls: 'str' };
      if (/^:\w+$/.test(tok)) return { text: tok, cls: 'var' };
      if (KEYWORDS.test(tok) && KEYWORDS.exec(tok)?.[0] === tok) return { text: tok, cls: 'kw' };
      return { text: tok, cls: 'plain' };
    });
  }
}
