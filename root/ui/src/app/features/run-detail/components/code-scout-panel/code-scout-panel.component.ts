import { Component, computed, input } from '@angular/core';

import { CodeGap, Remedy } from '../../../../core/models/run-state';

const NO_MATCH_COPY: Record<string, string> = {
  no_results: 'No candidate mechanism matched the search terms.',
  budget_exhausted: 'Search budget spent before a mechanism was isolated.',
  ambiguous: 'Several candidate mechanisms matched; none conclusive.',
};

/**
 * What each verdict may claim, and no more.
 *
 * `absent` deliberately does NOT say "confirmed missing" or "checked this
 * file" (PR #5, B2). The Remedy Loop searches the WHOLE REPO via
 * search_fn(repo, term) — there is no within-file check on main — so the
 * honest claim is "not found across N searches". A null status means the
 * loop never got to it, which is a different statement again (B3).
 */
function remedyCopy(r: Remedy, repo: string): string {
  const n = r.searched_terms?.length ?? 0;
  const searches = n ? `${n} search${n === 1 ? '' : 'es'}` : 'no searches recorded';
  switch (r.status) {
    case 'exists':
      return `Found in ${repo} — already present.`;
    case 'partial':
      return `Partial match in ${repo} — related code exists, not this exactly.`;
    case 'absent':
      return `Not found — ${searches} across ${repo}.`;
    default:
      return 'Not verified — the loop did not check this one.';
  }
}

interface CodeToken {
  text: string;
  cls: 'kw' | 'str' | 'var' | 'plain';
}

/**
 * Renders Agent 3's CodeGap[] with the Remedy Loop verdicts nested inside —
 * the shape the plan (rev 2.1) and the running backend both use.
 *
 * Two-part rendering per gap, mirroring what Code Scout actually does:
 *  1. the mechanism it pinned (file:line + snippet), and
 *  2. the remedies it proposed, each verified exists / absent / partial.
 *
 * `mechanism_found: false` is a first-class outcome enforced by
 * CodeGap.model_post_init on the Python side, not an error — it gets an
 * honest rendering rather than an empty card. The backend returns several of
 * these per run, so this is a common path, not an edge case.
 */
@Component({
  selector: 'app-code-scout-panel',
  templateUrl: './code-scout-panel.component.html',
  styleUrl: './code-scout-panel.component.scss',
})
export class CodeScoutPanelComponent {
  readonly gaps = input.required<CodeGap[]>();

  /** Gaps that pinned a mechanism, first and de-duplicated.
   *
   *  The backend can emit the same gap for several findings that route to
   *  the same repo (two findings both routing to pharmacy_checkout resolve
   *  to the same file), which would otherwise render as identical cards.
   *  Keyed on repo+file+line; the findings it covers are listed on the card. */
  readonly resolved = computed(() => {
    const byLocation = new Map<string, { gap: CodeGap; findingRanks: number[] }>();
    for (const gap of this.gaps().filter((g) => g.mechanism_found)) {
      const key = `${gap.repo}|${gap.file}|${gap.line}`;
      const hit = byLocation.get(key);
      if (hit) hit.findingRanks.push(gap.finding_rank);
      else byLocation.set(key, { gap, findingRanks: [gap.finding_rank] });
    }
    return [...byLocation.values()].sort((a, b) => a.findingRanks[0] - b.findingRanks[0]);
  });

  /** Searched, nothing pinned. Summarised rather than given a card each. */
  readonly unresolved = computed(() => this.gaps().filter((g) => !g.mechanism_found));

  gapClassLabel(gap: CodeGap): string {
    return gap.gap_class ? gap.gap_class.replace(/_/g, ' ').toUpperCase() : 'NO MECHANISM FOUND';
  }

  gapClassTone(gap: CodeGap): string {
    if (gap.gap_class === 'logic_flaw') return 'logic';
    if (gap.gap_class === 'ux_gap') return 'ux';
    return '';
  }

  noMatchCopy(gap: CodeGap): string {
    return (gap.no_match_reason && NO_MATCH_COPY[gap.no_match_reason]) || 'Not determined.';
  }

  remedyCopy(r: Remedy, repo: string): string {
    return remedyCopy(r, repo);
  }

  /** null status gets its own neutral tone — rendering "not verified" in the
   *  same red as "absent" was B3. */
  remedyTone(status: Remedy['status']): string {
    if (status === 'exists') return 'good';
    if (status === 'partial') return 'warn';
    if (status === 'absent') return 'gap';
    return 'unverified';
  }

  remedyLabel(status: Remedy['status']): string {
    return status ?? 'unverified';
  }

  tokenize(snippet: string | null | undefined): CodeToken[] {
    if (!snippet) return [];
    const KEYWORDS =
      /\b(private|final|String|public|Order|Override|SELECT|FROM|WHERE|AND|IN|INTERVAL|MINUTE|now|return|if|boolean|throw|new|try)\b/;
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
