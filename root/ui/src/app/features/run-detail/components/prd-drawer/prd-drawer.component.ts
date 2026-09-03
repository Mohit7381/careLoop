import { Component, computed, inject, input, output, signal } from '@angular/core';

import { buildPrdView } from '../../../../core/models/prd.model';
import { RunState } from '../../../../core/models/run-state';
import { DocxExportService } from '../../../../core/services/docx-export.service';
import { RunService } from '../../../../core/services/run.service';

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

  readonly prd = computed(() => buildPrdView(this.run()));

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
    const ok = await this.runService.deliver(this.run().run_id, channel);
    this.toast(ok ? 'Delivered to ' + channel : 'Draft approved · delivery unavailable');
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
