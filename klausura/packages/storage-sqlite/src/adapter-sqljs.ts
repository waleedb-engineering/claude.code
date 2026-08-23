import initSqlJs from 'sql.js';
import type { Database, SqlValue as SqlJsValue } from 'sql.js';
import type { Row, SqlValue, StoragePort } from '@klausura/ports';
import { migrate } from './migrator.js';
import type { PersistenceSink } from './persistence.js';

/**
 * StoragePort über sql.js (SQLite als WebAssembly).
 *
 * Dieser Adapter ist KEIN Auslieferungsziel — es gibt keine Web-Version des
 * Produkts (ADR-0001, Nachtrag 1). Er trägt Entwicklung, Tests und den
 * headless E2E-Lauf. Ausgeliefert wird über den Tauri-Adapter, der dieselben
 * Migrationen fährt und gegen denselben Vertragstest läuft.
 */

const FOREIGN_KEYS_ON = 'PRAGMA foreign_keys = ON';

let sqlJsPromise: Promise<Awaited<ReturnType<typeof initSqlJs>>> | undefined;

/**
 * Findet `sql-wasm.wasm`. Im Browser liefert Vite die Datei aus dem
 * Asset-Verzeichnis; in Node liegt sie unter einem Pfad, den nur der
 * Modulauflöser kennt (pnpm verlinkt in einen Store). Deshalb wird dort
 * aufgelöst statt geraten — ein fest verdrahteter Pfad bricht bei jedem
 * Wechsel des Paketmanagers.
 */
async function resolveWasm(file: string): Promise<string> {
  // Ueber globalThis geprueft statt ueber `window`: dieses Paket laeuft in
  // beiden Welten, und DOM-Typen gehoeren nicht in ein geteiltes Paket.
  if ('window' in globalThis) return `/sql-wasm/${file}`;
  const { createRequire } = await import('node:module');
  const require = createRequire(import.meta.url);
  return require.resolve(`sql.js/dist/${file}`);
}

async function loadSqlJs(): Promise<Awaited<ReturnType<typeof initSqlJs>>> {
  sqlJsPromise ??= (async () => {
    const wasmPath = await resolveWasm('sql-wasm.wasm');
    const dir = wasmPath.slice(0, wasmPath.lastIndexOf('/') + 1);
    return initSqlJs({ locateFile: (f: string) => `${dir}${f}` });
  })();
  return sqlJsPromise;
}

class SqlJsStorage implements StoragePort {
  #depth = 0;

  constructor(
    private readonly db: Database,
    private readonly sink: PersistenceSink,
  ) {}

  async run(sql: string, params: readonly SqlValue[] = []): Promise<void> {
    this.db.run(sql, params as SqlJsValue[]);
  }

  async all(sql: string, params: readonly SqlValue[] = []): Promise<readonly Row[]> {
    const stmt = this.db.prepare(sql);
    try {
      stmt.bind(params as SqlJsValue[]);
      const out: Row[] = [];
      while (stmt.step()) out.push(stmt.getAsObject() as Row);
      return out;
    } finally {
      stmt.free();
    }
  }

  async get(sql: string, params: readonly SqlValue[] = []): Promise<Row | undefined> {
    const rows = await this.all(sql, params);
    return rows[0];
  }

  /**
   * Verschachtelte Aufrufe teilen sich die äussere Transaktion — SQLite kennt
   * kein echtes Verschachteln, und ein zweites BEGIN würde werfen.
   */
  async transaction<T>(fn: () => Promise<T>): Promise<T> {
    if (this.#depth > 0) return fn();
    this.#depth++;
    this.db.run('BEGIN');
    try {
      const result = await fn();
      this.db.run('COMMIT');
      return result;
    } catch (error) {
      this.db.run('ROLLBACK');
      throw error;
    } finally {
      this.#depth--;
    }
  }

  /**
   * ACHTUNG: `export()` setzt `PRAGMA foreign_keys` auf 0 zurück — sql.js
   * schliesst und öffnet die Datenbank dabei intern. Ohne erneutes Setzen
   * wäre nach dem ersten Speichern jede Fremdschlüsselprüfung still
   * abgeschaltet. Verifiziert, nicht vermutet: siehe Test "erzwingt
   * Fremdschluessel auch nach dem Speichern".
   */
  #exportAndRestorePragmas(): Uint8Array {
    const bytes = this.db.export();
    this.db.run(FOREIGN_KEYS_ON);
    return bytes;
  }

  async persist(): Promise<void> {
    await this.sink.save(this.#exportAndRestorePragmas());
  }

  async close(): Promise<void> {
    await this.persist();
    this.db.close();
  }

  snapshot(): Uint8Array {
    return this.#exportAndRestorePragmas();
  }
}

export async function openSqlJsStorage(sink: PersistenceSink): Promise<StoragePort> {
  const SQL = await loadSqlJs();
  const existing = await sink.load();
  const db = new SQL.Database(existing ?? null);

  // Fremdschluessel sind in SQLite per Voreinstellung AUS. Ohne das haette
  // das Schema seine Referenzen nur als Kommentar.
  db.run(FOREIGN_KEYS_ON);

  const storage = new SqlJsStorage(db, sink);
  await migrate(storage, sink, () => storage.snapshot());
  return storage;
}
