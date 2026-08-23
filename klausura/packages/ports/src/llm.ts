/**
 * Nichts verlässt das Gerät ohne bestätigte Vorschau (docs/klausura/00, Block E).
 *
 * `preview` gibt zurück, WAS gesendet würde, ohne zu senden. Die Zustimmungs-UI
 * ruft ausschliesslich diese Methode auf. `send` ohne vorher bestätigtes
 * Preview-Token ist ein Fehler, kein Feature.
 */
export interface LlmRequest {
  readonly purpose: 'segmentation' | 'solution-extraction' | 'grading';
  readonly documentId: string;
  readonly text: string;
}

export interface LlmPreview {
  readonly token: string;
  readonly provider: string;
  readonly characterCount: number;
  /** Genau der Text, der das Gerät verlassen würde. */
  readonly payloadPreview: string;
}

export interface LlmPort {
  preview(request: LlmRequest): Promise<LlmPreview>;
  /** Nur mit einem Token aus `preview`, das der Nutzer bestätigt hat. */
  send(request: LlmRequest, confirmedToken: string): Promise<string>;
}
