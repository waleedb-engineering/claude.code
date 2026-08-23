/**
 * Vertrag steht, Implementierung kommt in M3 (docs/klausura/03).
 * In M1 existiert nur die Attrappe — kein OCR, kein Netz.
 */
export interface OcrBlock {
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  /** 0…1. Unter 0.7 markiert die Review-UI den Block. */
  readonly confidence: number;
}

export interface OcrPort {
  recognize(image: Uint8Array): Promise<readonly OcrBlock[]>;
}
