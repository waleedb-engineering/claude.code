import * as SQLite from 'expo-sqlite';
import type { Row, SqlValue, StoragePort } from '@klausura/ports';
import { migrate, type PersistenceSink } from '@klausura/storage-sqlite';

/**
 * StoragePort über expo-sqlite. Dieselben Migrationen und derselbe Vertrag
 * wie der sql.js-Adapter — nur liegt die Datei hier vom System aus dauerhaft
 * auf dem Gerät, weshalb `persist()` nichts zu tun hat.
 *
 * NICHT AUSGEFÜHRT GEPRÜFT: dieser Adapter braucht eine native Laufzeit
 * (Simulator oder Gerät). Er ist gegen die Typdeklarationen von
 * expo-sqlite 16 geschrieben, nicht aus dem Gedächtnis — aber bis er einmal
 * auf einem Gerät gelaufen ist, gilt er als unbestätigt.
 */
class ExpoStorage implements StoragePort {
  #depth = 0;

  constructor(private readonly db: SQLite.SQLiteDatabase) {}

  async run(sql: string, params: readonly SqlValue[] = []): Promise<void> {
    await this.db.runAsync(sql, params as SQLite.SQLiteBindParams);
  }

  async all(sql: string, params: readonly SqlValue[] = []): Promise<readonly Row[]> {
    return (await this.db.getAllAsync<Row>(sql, params as SQLite.SQLiteBindParams)) ?? [];
  }

  async get(sql: string, params: readonly SqlValue[] = []): Promise<Row | undefined> {
    return (await this.db.getFirstAsync<Row>(sql, params as SQLite.SQLiteBindParams)) ?? undefined;
  }

  /** Verschachtelte Aufrufe teilen sich die äussere Transaktion, wie bei sql.js. */
  async transaction<T>(fn: () => Promise<T>): Promise<T> {
    if (this.#depth > 0) return fn();
    this.#depth++;
    try {
      let result!: T;
      await this.db.withTransactionAsync(async () => { result = await fn(); });
      return result;
    } finally {
      this.#depth--;
    }
  }

  /** expo-sqlite schreibt in eine Datei; es gibt nichts zusätzlich zu sichern. */
  async persist(): Promise<void> {}

  async close(): Promise<void> { await this.db.closeAsync(); }

  snapshot(): Promise<Uint8Array> { return this.db.serializeAsync(); }
}

/**
 * expo-sqlite verwaltet die Datei selbst; diese Ablage kann keinen Snapshot
 * aufbewahren. `canBackup: false` ist deshalb keine Nachlässigkeit, sondern
 * eine Zusage an den Migrator: er verweigert jede destruktive Migration,
 * solange hier kein echter Backup-Pfad existiert.
 */
class SystemManagedSink implements PersistenceSink {
  readonly canBackup = false;
  async load(): Promise<Uint8Array | undefined> { return undefined; }
  async save(): Promise<void> {}
  async saveBackup(): Promise<void> {}
  async listBackups(): Promise<readonly number[]> { return []; }
  async loadBackup(): Promise<Uint8Array | undefined> { return undefined; }
}

let handle: Promise<StoragePort> | undefined;

export function db(): Promise<StoragePort> {
  handle ??= (async () => {
    const raw = await SQLite.openDatabaseAsync('klausura.db');
    // Fremdschluessel sind in SQLite per Voreinstellung AUS.
    await raw.execAsync('PRAGMA foreign_keys = ON');
    const storage = new ExpoStorage(raw);
    await migrate(storage, new SystemManagedSink(), () => storage.snapshot());
    return storage;
  })();
  return handle;
}
