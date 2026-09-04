import { Component, computed, input } from '@angular/core';

import { Suggestion, SuggestionType, VerificationStatus } from '../../../../core/models/run-state';

/**
 * Each verification status says a different thing, and none of them collapse
 * into a generic label.
 *
 * The two that get confused are the last two: `not_applicable` means there
 * was nothing to check — a process or commercial change has no code to
 * search for — while `unverified` means we could have checked and did not.
 * Rendering those alike would repeat PR #5's B3 in a new component.
 */
const VERIFICATION_COPY: Record<VerificationStatus, string> = {
  exists: 'Already built — found in the routed repo.',
  absent: 'Not found in the routed repo.',
  partial: 'Related code exists, but not this exactly.',
  not_applicable: 'Nothing to verify — not a code change.',
  unverified: 'Not checked against the code.',
};

/** How much weight the badge carries. `not_applicable` is deliberately
 *  neutral rather than a warning: it is the expected state for business and
 *  process ideas, not a shortfall. */
const VERIFICATION_TONE: Record<VerificationStatus, string> = {
  exists: 'good',
  absent: 'gap',
  partial: 'warn',
  not_applicable: 'na',
  unverified: 'unverified',
};

interface SuggestionGroup {
  findingRank: number;
  suggestions: Suggestion[];
}

/**
 * Renders Agent 3's Suggestion[] — improvement ideas, as opposed to the
 * CodeGap diagnoses next door.
 *
 * The distinction the badges protect: a `business` or `process` suggestion
 * is an opinion about what to do, carrying no code evidence by design. Only
 * `tech` suggestions can be verified against a repo, so only they get a
 * meaningful verdict. A commercial idea must never read as a code finding.
 */
@Component({
  selector: 'app-suggestions-panel',
  templateUrl: './suggestions-panel.component.html',
  styleUrl: './suggestions-panel.component.scss',
})
export class SuggestionsPanelComponent {
  readonly suggestions = input.required<Suggestion[]>();

  readonly groups = computed<SuggestionGroup[]>(() => {
    const byRank = new Map<number, Suggestion[]>();
    for (const s of this.suggestions()) {
      const list = byRank.get(s.finding_rank) ?? [];
      list.push(s);
      byRank.set(s.finding_rank, list);
    }
    // Tech first within a finding: the verified ones carry the most weight,
    // and a reader scanning for something actionable wants those on top.
    for (const list of byRank.values()) {
      list.sort((a, b) => this.typeRank(a.suggestion_type) - this.typeRank(b.suggestion_type));
    }
    return [...byRank.entries()]
      .sort(([a], [b]) => a - b)
      .map(([findingRank, suggestions]) => ({ findingRank, suggestions }));
  });

  readonly counts = computed(() => {
    const all = this.suggestions();
    return {
      total: all.length,
      tech: all.filter((s) => s.suggestion_type === 'tech').length,
      other: all.filter((s) => s.suggestion_type !== 'tech').length,
    };
  });

  private typeRank(t: SuggestionType): number {
    return t === 'tech' ? 0 : t === 'process' ? 1 : 2;
  }

  typeLabel(t: SuggestionType): string {
    return t.toUpperCase();
  }

  verificationLabel(s: VerificationStatus): string {
    return s.replace(/_/g, ' ');
  }

  verificationCopy(s: VerificationStatus): string {
    return VERIFICATION_COPY[s] ?? '';
  }

  verificationTone(s: VerificationStatus): string {
    return VERIFICATION_TONE[s] ?? 'na';
  }

  /** Only a tech suggestion can meaningfully cite a file. */
  showsEvidence(s: Suggestion): boolean {
    return s.suggestion_type === 'tech' && !!s.evidence_file;
  }
}
