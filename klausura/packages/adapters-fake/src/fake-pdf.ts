import type { PdfDocumentHandle, PdfPageInfo, PdfPort, PdfTextItem } from '@klausura/ports';

export interface FakePdfSpec {
  readonly pageCount: number;
  readonly hasTextLayer: boolean;
  readonly textByPage?: Readonly<Record<number, readonly PdfTextItem[]>>;
}

class FakePdfDocument implements PdfDocumentHandle {
  constructor(private readonly spec: FakePdfSpec) {}

  get pageCount(): number { return this.spec.pageCount; }
  get hasTextLayer(): boolean { return this.spec.hasTextLayer; }

  async page(pageNumber: number): Promise<PdfPageInfo> {
    if (pageNumber < 1 || pageNumber > this.spec.pageCount) {
      throw new Error(`Seite ${pageNumber} existiert nicht.`);
    }
    return { pageNumber, widthPt: 595, heightPt: 842 }; // A4
  }

  async textItems(pageNumber: number): Promise<readonly PdfTextItem[]> {
    return this.spec.textByPage?.[pageNumber] ?? [];
  }

  async render(): Promise<Uint8Array> {
    // 1x1 PNG. Reicht, um den Vertrag zu erfüllen; die Attrappe rendert nicht.
    return Uint8Array.from([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
  }

  async close(): Promise<void> {}
}

export class FakePdf implements PdfPort {
  constructor(private readonly spec: FakePdfSpec = { pageCount: 2, hasTextLayer: true }) {}
  async open(): Promise<PdfDocumentHandle> { return new FakePdfDocument(this.spec); }
}
