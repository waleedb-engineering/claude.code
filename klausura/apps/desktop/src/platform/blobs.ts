/**
 * Originaldateien liegen neben der Datenbank, nicht darin: sie sind gross,
 * binär und werden nie abgefragt — nur ganz gelesen.
 */
const DB_NAME = 'klausura-blobs';
const STORE = 'blobs';

function openIdb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(STORE); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('Blob-Ablage liess sich nicht oeffnen.'));
  });
}

function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openIdb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const req = fn(db.transaction(STORE, mode).objectStore(STORE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error ?? new Error('Blob-Zugriff fehlgeschlagen.'));
      }),
  );
}

export async function putBlob(key: string, data: Uint8Array): Promise<void> {
  const copy = new Uint8Array(data.length);
  copy.set(data);
  await tx('readwrite', (s) => s.put(copy.buffer, key));
}

export async function getBlob(key: string): Promise<Uint8Array | undefined> {
  const v = await tx<ArrayBuffer | undefined>('readonly', (s) => s.get(key));
  return v === undefined ? undefined : new Uint8Array(v);
}
