import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { buildPrdView } from '../../../../core/models/prd.model';
import { PrdDoc, PrdSection, humanSectionCount, isEdited, newSection, parsePrd, serialisePrd } from '../../../../core/models/prd-doc';
import { RunState } from '../../../../core/models/run-state';
import { DocxExportService } from '../../../../core/services/docx-export.service';
import { RunService } from '../../../../core/services/run.service';

@Component({
  selector: 'app-prd-drawer',
  imports: [FormsModule],
  templateUrl: './prd-drawer.component.html',
  styleUrl: './prd-drawer.component.scss',
})
export class PrdDrawerComponent {
  private readonly runService = inject(RunService);
  private readonly docx = inject(DocxExportService);

  readonly run = input.required<RunState>();
  readonly open = input(false);
  readonly closed = output<void>();

  readonly toastMessage = signal<string | null>(null);
  private toastTimer: ReturnType<typeof setTimeout> | null = null;

  /** Structured fallback, used only when the backend sent no prd_markdown
   *  (fixture-era runs, or a pipeline that stopped before the PRD node). */
  readonly prd = computed(() => buildPrdView(this.run()));

  /** True when we have the real generated document to render. */
  readonly hasMarkdown = computed(() => !!this.run().prd_draft?.trim());

  readonly doc = signal<PrdDoc | null>(null);
  readonly editing = signal(false);
  readonly editedCount = computed(() => { const d = this.doc(); return d ? humanSectionCount(d) : 0; });

  constructor() {
    // Re-parse whenever the run changes (a new poll, a different run). Any
    // in-progress edits belong to the old document, so they are dropped
    // rather than silently re-attached to different content.
    effect(() => {
      const md = this.run().prd_draft;
      this.doc.set(md?.trim() ? parsePrd(md) : null);
      this.editing.set(false);
    });
  }

  toggleEdit(): void {
    this.editing.set(!this.editing());
  }

  /** Mark a section as human-touched the first time it actually changes.
   *  An untouched agent section keeps its provenance even if focused. */
  onSectionInput(section: PrdSection, body: string): void {
    this.doc.update((d) => {
      if (!d) return d;
      const sections = d.sections.map((s) =>
        s.id === section.id
          ? { ...s, body, origin: s.origin === 'agent' && body !== s.original ? ('human-edited' as const) : s.origin }
          : s
      );
      return { ...d, sections };
    });
  }

  onHeadingInput(section: PrdSection, heading: string): void {
    this.doc.update((d) => {
      if (!d) return d;
      const sections = d.sections.map((s) =>
        s.id === section.id ? { ...s, heading, origin: s.origin === 'agent' ? ('human-edited' as const) : s.origin } : s
      );
      return { ...d, sections };
    });
  }

  addSection(afterId?: string): void {
    this.doc.update((d) => {
      if (!d) return d;
      const s = newSection();
      const i = afterId ? d.sections.findIndex((x) => x.id === afterId) + 1 : d.sections.length;
      const sections = [...d.sections];
      sections.splice(i, 0, s);
      return { ...d, sections };
    });
    this.editing.set(true);
  }

  removeSection(id: string): void {
    this.doc.update((d) => (d ? { ...d, sections: d.sections.filter((s) => s.id !== id) } : d));
  }

  move(id: string, delta: -1 | 1): void {
    this.doc.update((d) => {
      if (!d) return d;
      const i = d.sections.findIndex((s) => s.id === id);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= d.sections.length) return d;
      const sections = [...d.sections];
      [sections[i], sections[j]] = [sections[j], sections[i]];
      return { ...d, sections };
    });
  }

  /** Restore one section to what the agent wrote. */
  revertSection(id: string): void {
    this.doc.update((d) => {
      if (!d) return d;
      const sections = d.sections.map((s) =>
        s.id === id && s.original !== undefined ? { ...s, body: s.original, origin: 'agent' as const } : s
      );
      return { ...d, sections };
    });
  }

  /** Throw away every edit and re-parse the backend's document. */
  revertAll(): void {
    const md = this.run().prd_draft;
    this.doc.set(md?.trim() ? parsePrd(md) : null);
    this.toast('Reverted to the generated PRD');
  }

  isEdited(s: PrdSection): boolean {
    return isEdited(s);
  }

  originLabel(s: PrdSection): string {
    return s.origin === 'human-added' ? 'ADDED BY YOU · UNVERIFIED' : 'EDITED BY YOU · UNVERIFIED';
  }

  /** The edited markdown — what a future POST /prd/revisions would send, and
   *  what the .docx export uses so a download matches the screen. */
  currentMarkdown(): string {
    const d = this.doc();
    return d ? serialisePrd(d) : (this.run().prd_draft ?? '');
  }

  close(): void {
    this.closed.emit();
  }

  async downloadDocx(): Promise<void> {
    await this.docx.download(this.run(), this.prd(), this.hasMarkdown() ? this.currentMarkdown() : undefined);
    this.toast('Downloading ' + this.docxFilename());
  }

  private docxFilename(): string {
    return `CareLoop_PRD_run${this.run().run_id}_${this.prd().title.replace(/\W+/g, '_')}.docx`;
  }

  /**
   * Optimistic by design — the toast fires before the network call
   * resolves, so a slow or dead Garuda/GChat integration (no verified
   * GChat channel type exists yet — see README "Known gaps") can never
   * produce a dead moment on stage. It then upgrades or quietly downgrades
   * once the (currently unimplemented) deliver endpoint responds.
   */
  async approve(): Promise<void> {
    const channel = this.prd().channel;
    this.close();
    this.toast('Sent to ' + channel);
    const res = await this.runService.deliver(this.run().run_id);
    this.toast(res.delivered ? 'Delivered to ' + channel : 'Draft approved · delivery unavailable');
  }

  requestChanges(): void {
    this.close();
    this.toast('Sent back for changes');
  }

  private toast(message: string): void {
    this.toastMessage.set(message);
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toastMessage.set(null), 2600);
  }
}
