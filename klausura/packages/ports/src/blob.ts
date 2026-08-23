/** Originaldateien und Seitenraster. Getrennt von der Datenbank, weil binär und gross. */
export interface BlobPort {
  put(key: string, data: Uint8Array): Promise<void>;
  get(key: string): Promise<Uint8Array | undefined>;
  has(key: string): Promise<boolean>;
  delete(key: string): Promise<void>;
}
