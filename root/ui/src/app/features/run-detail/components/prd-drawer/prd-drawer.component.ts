import { Component, computed, effect, inject, input, output, signal } from '@angular/core';

import { buildPrdView, renderPrdMarkdown } from '../../../../core/models/prd.model';
import { PrdSummary, RunState } from '../../../../core/models/run-state';
import { DocxExportService } from '../../../../core/services/docx-export.service';
import { RunService } from '../../../../core/services/run.service';

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

@Component({
  selector: 'app-prd-drawer',
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

  /** Which finding's PRD is on screen. Backend PRDs are keyed by finding
   *  rank (one per finding, up to MAX_PRDS_PER_RUN); the fixture has no
   *  `prds[]` yet, so ranks there fall back to one card per finding. */
  readonly selectedRank = signal(1);

  readonly prdRanks = computed<number[]>(() => {
    const run = this.run();
    if (run.prds.length) return [...run.prds].map((p) => p.finding_rank).sort((a, b) => a - b);
    return [...run.findings].map((f) => f.rank).sort((a, b) => a - b).slice(0, 5);
  });

  /** Real markdown artifact for the selected finding, if the backend wrote
   *  one — null in fixture mode or against an older backend, in which case
   *  the drawer falls back to the reconstructed structured view below. */
  readonly activeSummary = computed<PrdSummary | null>(() => {
    const rank = this.selectedRank();
    return this.run().prds.find((p) => p.finding_rank === rank) ?? null;
  });

  readonly markdownHtml = computed<string | null>(() => {
    const summary = this.activeSummary();
    return summary ? renderPrdMarkdown(summary.markdown) : null;
  });

  /** Structured fallback — always computed so the "Approve"/docx flows keep
   *  working even when a real markdown artifact is on screen. */
  readonly prd = computed(() => buildPrdView(this.run(), this.selectedRank()));

  /** Chat editing only makes sense against a real backend artifact: the
   *  endpoint reads/writes a RunArtifact row keyed by this run's id, which
   *  the frozen fixture (run 47) doesn't have. Gate on the live source
   *  rather than silently no-oping the button. */
  readonly chatAvailable = computed(() => this.runService.source() === 'live');

  private readonly chatLogs = signal<Record<number, ChatMessage[]>>({});
  readonly chatLog = computed<ChatMessage[]>(() => this.chatLogs()[this.selectedRank()] ?? []);
  readonly chatInput = signal('');
  readonly chatBusy = signal(false);

  constructor() {
    // Keep the selection valid as the run/prds change (e.g. fixture -> live).
    effect(() => {
      const ranks = this.prdRanks();
      if (ranks.length && !ranks.includes(this.selectedRank())) {
        this.selectedRank.set(ranks[0]);
      }
    });
  }

  selectRank(rank: number): void {
    this.selectedRank.set(rank);
  }

  isEdited(rank: number): boolean {
    return this.run().prds.find((p) => p.finding_rank === rank)?.edited ?? false;
  }

  close(): void {
    this.closed.emit();
  }

  async downloadDocx(): Promise<void> {
    await this.docx.download(this.run(), this.prd());
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

  async sendChat(): Promise<void> {
    const message = this.chatInput().trim();
    if (!message || this.chatBusy() || !this.chatAvailable()) return;

    const rank = this.selectedRank();
    this.appendChat(rank, 'user', message);
    this.chatInput.set('');
    this.chatBusy.set(true);

    const res = await this.runService.chatOnPrd(this.run().run_id, rank, message);

    this.chatBusy.set(false);
    if ('error' in res) {
      this.appendChat(rank, 'assistant', `Couldn't reach the PRD editor: ${res.error}`);
      return;
    }
    this.appendChat(rank, 'assistant', res.reply);
  }

  private appendChat(rank: number, role: ChatMessage['role'], text: string): void {
    this.chatLogs.update((logs) => ({ ...logs, [rank]: [...(logs[rank] ?? []), { role, text }] }));
  }

  private toast(message: string): void {
    this.toastMessage.set(message);
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toastMessage.set(null), 2600);
  }
}
