/**
 * Wohin die Datenbankdatei geht. Der Adapter kennt nur diesen Vertrag, damit
 * derselbe Code im Browser (IndexedDB), in Node (Datei) und im Test
 * (Speicher) läuft.
 */
export interface PersistenceSink {
  /**
   * Kann diese Ablage einen Snapshot aufbewahren? Wo das nicht geht (etwa bei
   * einer vom System verwalteten Datei), verweigert der Migrator jede
   * destruktive Migration, statt ohne Rückweg zu arbeiten.
   */
  readonly canBackup: boolean;
  load(): Promise<Uint8Array | undefined>;
  save(data: Uint8Array): Promise<void>;
  /** Snapshot vor einer Migration. Es gibt keine Cloud-Kopie. */
  saveBackup(version: number, data: Uint8Array): Promise<void>;
  listBackups(): Promise<readonly number[]>;
  loadBackup(version: number): Promise<Uint8Array | undefined>;
}

/** Für Tests und für den Neustart-Nachweis: derselbe Sink, neue Datenbank. */
export class MemorySink implements PersistenceSink {
  readonly canBackup = true;
  #data: Uint8Array | undefined;
  readonly #backups = new Map<number, Uint8Array>();

  async load(): Promise<Uint8Array | undefined> { return this.#data; }
  async save(data: Uint8Array): Promise<void> { this.#data = data; }
  async saveBackup(version: number, data: Uint8Array): Promise<void> { this.#backups.set(version, data); }
  async listBackups(): Promise<readonly number[]> { return [...this.#backups.keys()].sort((a, b) => a - b); }
  async loadBackup(version: number): Promise<Uint8Array | undefined> { return this.#backups.get(version); }
}
