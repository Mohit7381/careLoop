import { Injectable } from '@angular/core';
import JSZip from 'jszip';

import { PrdView } from '../models/prd.model';
import { RunState } from '../models/run-state';

/**
 * PRD -> .docx, entirely client-side. A .docx is a zip of three OOXML
 * parts; JSZip builds it in the browser, so there is no backend endpoint
 * for this and no server round-trip. Uses direct run formatting rather
 * than named styles, so no styles.xml part is needed and Word / Google
 * Docs / Pages all open the result.
 *
 * Ported from the original HTML prototype's downloadDocx()/prdBodyXml().
 */
@Injectable({ providedIn: 'root' })
export class DocxExportService {
  /**
   * `markdown`, when supplied, is the document currently on screen — the
   * real prd_markdown plus any edits the user made. Exporting that rather
   * than the structured reconstruction means the download always matches
   * what was being read, edits included.
   */
  async download(run: RunState, prd: PrdView, markdown?: string): Promise<void> {
    const zip = new JSZip();

    zip.file(
      '[Content_Types].xml',
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`
    );
    zip.folder('_rels')!.file(
      '.rels',
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`
    );
    zip.folder('word')!.file(
      'document.xml',
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${this.bodyXml(
        run,
        prd
      )}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>`
    );

    const blob = await zip.generateAsync({
      type: 'blob',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    const filename = `CareLoop_PRD_run${run.run_id}_${prd.title.replace(/\W+/g, '_')}.docx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 1500);
  }

  /** Render generated markdown to OOXML paragraphs: headings bold and
   *  larger, list items bulleted, everything else a plain paragraph. Good
   *  enough for a PRD; this is not a general markdown engine. */
  private markdownXml(markdown: string): string {
    const out: string[] = [];
    for (const raw of markdown.split('\n')) {
      const line = raw.trimEnd();
      if (!line.trim()) continue;
      const h = /^(#{1,4})\s+(.*)$/.exec(line);
      if (h) {
        const size = h[1].length === 1 ? 36 : h[1].length === 2 ? 28 : 24;
        out.push(this.para(h[2], { size, bold: true, before: 220, after: 90 }));
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        out.push(this.para('•  ' + line.replace(/^[-*]\s+/, ''), { size: 22, after: 60 }));
        continue;
      }
      if (/^\|/.test(line)) {
        // Table rows render as monospace-ish plain lines rather than a real
        // OOXML table — readable, and avoids a half-built table renderer.
        out.push(this.para(line.replace(/\|/g, ' '), { size: 20, after: 40 }));
        continue;
      }
      out.push(this.para(line.replace(/\*\*(.+?)\*\*/g, '$1'), { size: 22 }));
    }
    return out.join('');
  }

  private bodyXml(run: RunState, prd: PrdView): string {
    const out: string[] = [];
    out.push(this.para(prd.title, { size: 36, bold: true, after: 60 }));
    out.push(this.para(prd.subtitle, { size: 18, color: '6A7F86', after: 80 }));
    out.push(this.para(prd.banner, { size: 18, bold: true, color: 'A06508', after: 240 }));

    out.push(this.para('Overview', { size: 26, bold: true, before: 200, after: 80 }));
    out.push(this.para(prd.overview));

    out.push(this.para('Goals', { size: 26, bold: true, before: 200, after: 80 }));
    out.push(this.table([['Goal', 'Target'], ...prd.goals]));

    out.push(this.para('Functional requirements', { size: 26, bold: true, before: 200, after: 80 }));
    prd.requirements.forEach(([id, text]) => out.push(this.para(`${id}   ${text}`, { size: 22, after: 80 })));

    out.push(this.para('Open questions', { size: 26, bold: true, before: 200, after: 80 }));
    out.push(this.table([['Question', 'Owner'], ...prd.openQuestions]));

    out.push(
      this.para(
        `Generated by CareLoop run #${run.run_id} · window ${run.window_start} to ${run.window_end} · DRAFT, needs human review`,
        { size: 16, color: '6A7F86', before: 320 }
      )
    );
    return out.join('');
  }

  private para(
    text: string,
    opts: { size?: number; bold?: boolean; before?: number; after?: number; color?: string } = {}
  ): string {
    const { size = 22, bold = false, before = 0, after = 120, color } = opts;
    return (
      `<w:p><w:pPr><w:spacing w:before="${before}" w:after="${after}"/></w:pPr><w:r><w:rPr>` +
      (bold ? '<w:b/>' : '') +
      `<w:sz w:val="${size}"/><w:szCs w:val="${size}"/>` +
      (color ? `<w:color w:val="${color}"/>` : '') +
      `</w:rPr><w:t xml:space="preserve">${this.esc(text)}</w:t></w:r></w:p>`
    );
  }

  private cell(text: string, bold = false, w = 4600): string {
    return `<w:tc><w:tcPr><w:tcW w:w="${w}" w:type="dxa"/></w:tcPr>${this.para(text, {
      size: 20,
      bold,
      after: 40,
    })}</w:tc>`;
  }

  private table(rows: [string, string][]): string {
    const borders = ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']
      .map((b) => `<w:${b} w:val="single" w:sz="4" w:color="C8D4D9"/>`)
      .join('');
    const body = rows.map(([a, b], i) => `<w:tr>${this.cell(a, i === 0)}${this.cell(b, i === 0)}</w:tr>`).join('');
    return (
      `<w:tbl><w:tblPr><w:tblW w:w="9200" w:type="dxa"/><w:tblBorders>${borders}</w:tblBorders></w:tblPr>${body}</w:tbl>` +
      this.para('', { after: 120 })
    );
  }

  private esc(t: string): string {
    return String(t)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}
