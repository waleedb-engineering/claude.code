import type { LlmPort, LlmPreview, LlmRequest } from '@klausura/ports';

/**
 * Attrappe, die die Zustimmungsregel HART durchsetzt: `send` ohne bestätigtes
 * Token wirft. Damit fällt eine Verletzung im Test auf, nicht erst im Produkt.
 */
export class FakeLlm implements LlmPort {
  readonly #issued = new Set<string>();
  #counter = 0;
  readonly sent: LlmRequest[] = [];

  async preview(request: LlmRequest): Promise<LlmPreview> {
    const token = `preview-${++this.#counter}`;
    this.#issued.add(token);
    return {
      token,
      provider: 'fake',
      characterCount: request.text.length,
      payloadPreview: request.text,
    };
  }

  async send(request: LlmRequest, confirmedToken: string): Promise<string> {
    if (!this.#issued.has(confirmedToken)) {
      throw new Error('send() ohne bestaetigte Vorschau. Nichts verlaesst das Geraet ungefragt.');
    }
    this.sent.push(request);
    return '';
  }
}
