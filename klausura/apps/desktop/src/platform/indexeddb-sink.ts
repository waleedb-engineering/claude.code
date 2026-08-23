import type { PersistenceSink } from '@klausura/storage-sqlite';

const DB_NAME = 'klausura';
const STORE = 'sqlite';
const MAIN_KEY = 'main';
const BACKUP_PREFIX = 'backup:';
/** Drei Snapshots reichen; es gibt keine Cloud-Kopie, aber auch keinen Platz für beliebig viele. */
const MAX_BACKUPS = 3;

function openIdb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(STORE); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB liess sich nicht oeffnen.'));
  });
}

function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openIdb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const store = db.transaction(STORE, mode).objectStore(STORE);
        const req = fn(store);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error ?? new Error('IndexedDB-Zugriff fehlgeschlagen.'));
      }),
  );
}

/**
 * Ablage der Datenbankdatei im Browser. Im Tauri-Build tritt an diese Stelle
 * eine Datei im App-Verzeichnis — der Vertrag bleibt derselbe.
 */
export class IndexedDbSink implements PersistenceSink {
  readonly canBackup = true;

  async load(): Promise<Uint8Array | undefined> {
    const v = await tx<ArrayBuffer | undefined>('readonly', (s) => s.get(MAIN_KEY));
    return v === undefined ? undefined : new Uint8Array(v);
  }

  async save(data: Uint8Array): Promise<void> {
    await tx('readwrite', (s) => s.put(toBuffer(data), MAIN_KEY));
  }

  async saveBackup(version: number, data: Uint8Array): Promise<void> {
    await tx('readwrite', (s) => s.put(toBuffer(data), `${BACKUP_PREFIX}${version}`));
    const versions = await this.listBackups();
    for (const old of versions.slice(0, Math.max(0, versions.length - MAX_BACKUPS))) {
      await tx('readwrite', (s) => s.delete(`${BACKUP_PREFIX}${old}`));
    }
  }

  async listBackups(): Promise<readonly number[]> {
    const keys = await tx<IDBValidKey[]>('readonly', (s) => s.getAllKeys());
    return keys
      .filter((k): k is string => typeof k === 'string' && k.startsWith(BACKUP_PREFIX))
      .map((k) => Number(k.slice(BACKUP_PREFIX.length)))
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b);
  }

  async loadBackup(version: number): Promise<Uint8Array | undefined> {
    const v = await tx<ArrayBuffer | undefined>('readonly', (s) => s.get(`${BACKUP_PREFIX}${version}`));
    return v === undefined ? undefined : new Uint8Array(v);
  }
}

/** Kopie in einen eigenen ArrayBuffer — sql.js kann eine Sicht auf den wasm-Heap liefern. */
function toBuffer(data: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(data.length);
  copy.set(data);
  return copy.buffer;
}
