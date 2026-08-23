export type SqlValue = string | number | null | Uint8Array;
export type Row = Readonly<Record<string, SqlValue>>;

export interface StoragePort {
  /** Führt eine schreibende Anweisung aus. */
  run(sql: string, params?: readonly SqlValue[]): Promise<void>;
  /** Liest Zeilen. */
  all(sql: string, params?: readonly SqlValue[]): Promise<readonly Row[]>;
  /** Liest höchstens eine Zeile. */
  get(sql: string, params?: readonly SqlValue[]): Promise<Row | undefined>;
  /** Alles oder nichts. Wirft der Rumpf, wird zurückgerollt. */
  transaction<T>(fn: () => Promise<T>): Promise<T>;
  /** Schreibt den aktuellen Stand dauerhaft weg (Browser: IndexedDB, Tauri: Datei). */
  persist(): Promise<void>;
  close(): Promise<void>;
}
