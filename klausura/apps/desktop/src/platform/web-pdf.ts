import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import type { PDFDocumentProxy, TextItem } from 'pdfjs-dist/types/src/display/api.js';
import type { PdfDocumentHandle, PdfPageInfo, PdfPort, PdfTextItem } from '@klausura/ports';
import workerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

class WebPdfDocument implements PdfDocumentHandle {
  constructor(
    private readonly doc: PDFDocumentProxy,
    readonly hasTextLayer: boolean,
  ) {}

  get pageCount(): number { return this.doc.numPages; }

  async page(pageNumber: number): Promise<PdfPageInfo> {
    const p = await this.doc.getPage(pageNumber);
    const v = p.getViewport({ scale: 1 });
    return { pageNumber, widthPt: v.width, heightPt: v.height };
  }

  async textItems(pageNumber: number): Promise<readonly PdfTextItem[]> {
    const p = await this.doc.getPage(pageNumber);
    const v = p.getViewport({ scale: 1 });
    const content = await p.getTextContent();
    const out: PdfTextItem[] = [];
    for (const item of content.items) {
      if (!('str' in item)) continue;
      const t = item as TextItem;
      // transform ist [a,b,c,d,e,f]; e/f sind x/y in PDF-Koordinaten mit
      // Ursprung unten links. Normalisiert und auf oben links gedreht.
      const [, , , , e, f] = t.transform as [number, number, number, number, number, number];
      out.push({
        text: t.str,
        x: e / v.width,
        y: 1 - f / v.height,
        width: t.width / v.width,
        height: t.height / v.height,
      });
    }
    return out;
  }

  /** Rendert in ein Canvas und gibt PNG-Bytes zurück. */
  async render(pageNumber: number, targetWidthPx: number): Promise<Uint8Array> {
    const canvas = await this.renderToCanvas(pageNumber, targetWidthPx);
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/png'));
    if (blob === null) throw new Error('Seite liess sich nicht in ein Bild umwandeln.');
    return new Uint8Array(await blob.arrayBuffer());
  }

  /** Direkter Weg für die Anzeige — spart den Umweg über PNG-Bytes. */
  async renderToCanvas(pageNumber: number, targetWidthPx: number): Promise<HTMLCanvasElement> {
    const p = await this.doc.getPage(pageNumber);
    const base = p.getViewport({ scale: 1 });
    const viewport = p.getViewport({ scale: targetWidthPx / base.width });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);
    const ctx = canvas.getContext('2d');
    if (ctx === null) throw new Error('Kein 2D-Kontext verfuegbar.');
    await p.render({ canvas, canvasContext: ctx, viewport }).promise;
    return canvas;
  }

  async close(): Promise<void> { await this.doc.destroy(); }
}

export class WebPdf implements PdfPort {
  async open(data: Uint8Array): Promise<WebPdfDocument> {
    // pdf.js übernimmt den Puffer; eine Kopie verhindert, dass der Aufrufer
    // hinterher auf einen geleerten Puffer schaut.
    const copy = new Uint8Array(data.length);
    copy.set(data);
    const doc = await getDocument({ data: copy }).promise;

    const first = await doc.getPage(1);
    const content = await first.getTextContent();
    const hasTextLayer = content.items.some((i) => 'str' in i && (i as TextItem).str.trim() !== '');

    return new WebPdfDocument(doc, hasTextLayer);
  }
}

export const webPdf = new WebPdf();
