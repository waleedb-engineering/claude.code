export interface PdfPageInfo {
  readonly pageNumber: number;
  readonly widthPt: number;
  readonly heightPt: number;
}

export interface PdfTextItem {
  readonly text: string;
  /** Normalisierte Seitenkoordinaten, 0…1. */
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface PdfDocumentHandle {
  readonly pageCount: number;
  readonly hasTextLayer: boolean;
  page(pageNumber: number): Promise<PdfPageInfo>;
  /** Textlayer der Seite. Leer, wenn das Dokument keinen hat. */
  textItems(pageNumber: number): Promise<readonly PdfTextItem[]>;
  /** Seite als PNG-Bytes in der gewünschten Breite. */
  render(pageNumber: number, targetWidthPx: number): Promise<Uint8Array>;
  close(): Promise<void>;
}

export interface PdfPort {
  open(data: Uint8Array): Promise<PdfDocumentHandle>;
}
