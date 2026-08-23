import type { OcrBlock, OcrPort } from '@klausura/ports';

export class FakeOcr implements OcrPort {
  constructor(private readonly blocks: readonly OcrBlock[] = []) {}
  async recognize(): Promise<readonly OcrBlock[]> { return this.blocks; }
}
