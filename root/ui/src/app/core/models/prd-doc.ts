/**
 * The PRD as a list of editable sections.
 *
 * `prd_markdown` on RunDetailResponse is the real generated document — the
 * one the PRD Generator wrote and the one `/runs/{id}/prd` serves. Until now
 * the drawer ignored it entirely and rendered a client-side reconstruction
 * (`buildPrdView`), so a live run showed something the backend never
 * produced. This parses the real document instead, splitting on `##`
 * headings so each section can be edited in place and reassembled without
 * the markdown ever stopping being the source of truth.
 *
 * Provenance is tracked per section and is deliberately one-way: anything a
 * human writes is marked `human` and never renders like agent output. An
 * edited requirement is an opinion until something re-verifies it, and the
 * screen should not launder it into a verified finding — the same rule the
 * Remedy Loop verdicts follow.
 */
export type SectionOrigin = 'agent' | 'human-edited' | 'human-added';

export interface PrdSection {
  id: string;
  /** Heading text without the leading `##`. Empty for any preamble that
   *  appears before the first heading. */
  heading: string;
  /** Heading depth (2 for `##`, 3 for `###`) so reassembly round-trips. */
  level: number;
  body: string;
  origin: SectionOrigin;
  /** The agent's original body, kept so an edit can be reverted. */
  original?: string;
}

export interface PrdDoc {
  title: string;
  /** Everything above the first `##`, typically the H1 and the DRAFT banner. */
  preamble: string;
  sections: PrdSection[];
}

let seq = 0;
const nextId = () => `s${++seq}`;

/** Split a generated PRD into sections. Anything before the first `##`
 *  becomes the preamble, so the DRAFT banner and title are never editable
 *  by accident. */
export function parsePrd(markdown: string): PrdDoc {
  const lines = (markdown ?? '').split('\n');
  const title = (lines.find((l) => l.startsWith('# ')) ?? '# Product Requirements Document').replace(/^#\s+/, '');

  const preamble: string[] = [];
  const sections: PrdSection[] = [];
  let current: PrdSection | null = null;

  for (const line of lines) {
    const m = /^(#{2,3})\s+(.*)$/.exec(line);
    if (m) {
      if (current) sections.push(current);
      current = {
        id: nextId(),
        level: m[1].length,
        heading: m[2].trim(),
        body: '',
        origin: 'agent',
      };
      continue;
    }
    if (current) current.body += line + '\n';
    else preamble.push(line);
  }
  if (current) sections.push(current);

  for (const s of sections) {
    s.body = s.body.replace(/\n+$/, '');
    s.original = s.body;
  }

  return { title, preamble: preamble.join('\n').trim(), sections };
}

/** Reassemble to markdown. Round-trips an unedited document unchanged apart
 *  from trailing whitespace, so the .docx export and any future
 *  POST /prd/revisions both take the same string. */
export function serialisePrd(doc: PrdDoc): string {
  const out: string[] = [];
  if (doc.preamble) out.push(doc.preamble, '');
  for (const s of doc.sections) {
    out.push(`${'#'.repeat(s.level)} ${s.heading}`, '');
    if (s.body.trim()) out.push(s.body.trim(), '');
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

export function newSection(): PrdSection {
  return { id: nextId(), level: 2, heading: 'New section', body: '', origin: 'human-added' };
}

export function isEdited(s: PrdSection): boolean {
  return s.origin !== 'agent';
}

/** Count of sections a human touched — surfaced in the drawer so the
 *  provenance of the document as a whole is visible, not just per section. */
export function humanSectionCount(doc: PrdDoc): number {
  return doc.sections.filter(isEdited).length;
}
