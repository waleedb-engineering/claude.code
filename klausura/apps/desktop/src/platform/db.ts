import { openSqlJsStorage } from '@klausura/storage-sqlite';
import type { StoragePort } from '@klausura/ports';
import { IndexedDbSink } from './indexeddb-sink.js';

/**
 * Eine Datenbankverbindung für die Laufzeit der App.
 *
 * Im Tauri-Build tritt hier der rusqlite-Adapter an die Stelle von sql.js —
 * dieselben Migrationen, derselbe Vertrag (ADR-0001, Nachtrag 1).
 */
let handle: Promise<StoragePort> | undefined;

export function db(): Promise<StoragePort> {
  handle ??= openSqlJsStorage(new IndexedDbSink());
  return handle;
}
