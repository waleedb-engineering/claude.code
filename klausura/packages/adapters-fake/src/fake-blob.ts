import type { BlobPort } from '@klausura/ports';

export class FakeBlobStore implements BlobPort {
  readonly #data = new Map<string, Uint8Array>();

  async put(key: string, data: Uint8Array): Promise<void> { this.#data.set(key, data); }
  async get(key: string): Promise<Uint8Array | undefined> { return this.#data.get(key); }
  async has(key: string): Promise<boolean> { return this.#data.has(key); }
  async delete(key: string): Promise<void> { this.#data.delete(key); }
}
