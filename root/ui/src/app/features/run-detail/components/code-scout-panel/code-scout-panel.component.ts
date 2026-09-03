import { Component, computed, input } from '@angular/core';

import { Suggestion, SuggestionType, VerificationStatus } from '../../../../core/models/run-state';

const VERIFICATION_COPY: Record<VerificationStatus, string> = {
  exists: 'Already built — found wired into this mechanism.',
  absent: 'Checked this file — not built.',
  partial: 'Exists in this file, but not wired into this mechanism.',
  not_applicable: 'No code to verify — business/process change.',
};

export interface ExploredAnchor {
  file: string;
  line: number;
  snippet: string;
}

interface CodeToken {
  text: string;
  cls: 'kw' | 'str' | 'var' | 'plain';
}

interface FindingGroup {
  findingRank: number;
  repo: string | null;
  anchor: ExploredAnchor | null;
  suggestions: Suggestion[];
}

/**
 * Renders Suggestion[] from Agent 3 (Code Scout) — Rev 3's "explore and
 * suggest" flow, replacing the single-CodeGap "money moment" panel.
 *
 * Two-part rendering per finding, matching the real pipeline's two steps:
 *  1. "Explored" — the mechanism Code Scout's search actually located
 *     (file:line + snippet). NOTE: this comes from `anchors`, NOT from the
 *     Suggestion contract — contracts.py's Suggestion has no snippet field,
 *     only evidence_file/evidence_line. `anchors` is fixture-only UI
 *     enrichment (see run-47.fixture.ts), matching the real inventory in
 *     impl/codeScout's fixtures/code_scout/*.json. Flagged in the README
 *     rather than worked around silently — ask Harshit whether
 *     Suggestion should carry the snippet, or whether file:line is enough.
 *  2. Suggestions — 0..N cards, tech (code-verified) mixed with
 *     business/process (unverifiable by design, no code to check).
 */
@Component({
  selector: 'app-code-scout-panel',
  templateUrl: './code-scout-panel.component.html',
  styleUrl: './code-scout-panel.component.scss',
})
export class CodeScoutPanelComponent {
  readonly suggestions = input.required<Suggestion[]>();
  readonly anchors = input<Record<number, ExploredAnchor>>({});

  readonly groups = computed<FindingGroup[]>(() => {
    const byRank = new Map<number, Suggestion[]>();
    for (const s of this.suggestions()) {
      const list = byRank.get(s.finding_rank) ?? [];
      list.push(s);
      byRank.set(s.finding_rank, list);
    }
    const anchors = this.anchors();
    return [...byRank.entries()]
      .sort(([a], [b]) => a - b)
      .map(([findingRank, suggestions]) => ({
        findingRank,
        repo: suggestions[0]?.repo ?? null,
        anchor: anchors[findingRank] ?? null,
        suggestions,
      }));
  });

  typeLabel(t: SuggestionType): string {
    return t.toUpperCase();
  }

  verificationCopy(status: VerificationStatus): string {
    return VERIFICATION_COPY[status];
  }

  verificationTone(status: VerificationStatus): string {
    if (status === 'exists') return 'good';
    if (status === 'partial') return 'warn';
    if (status === 'absent') return 'gap';
    return 'na';
  }

  /** Snippets are fixture-only (see class doc) — tokenized the same way
   *  the Rev 2 panel did, kept for visual continuity. */
  tokenize(snippet: string | null | undefined): CodeToken[] {
    if (!snippet) return [];
    const KEYWORDS =
      /\b(private|final|String|public|Order|Override|SELECT|FROM|WHERE|AND|IN|INTERVAL|MINUTE|now|return|if|boolean|throw|new)\b/;
    return snippet
      .split(/(\s+|\b)/)
      .filter(Boolean)
      .map((tok) => {
        if (/^'[^']*'$/.test(tok)) return { text: tok, cls: 'str' as const };
        if (/^:\w+$/.test(tok)) return { text: tok, cls: 'var' as const };
        if (KEYWORDS.test(tok) && KEYWORDS.exec(tok)?.[0] === tok) return { text: tok, cls: 'kw' as const };
        return { text: tok, cls: 'plain' as const };
      });
  }
}
