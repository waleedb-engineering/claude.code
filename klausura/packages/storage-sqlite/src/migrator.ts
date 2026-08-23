import type { StoragePort } from '@klausura/ports';
import { LATEST_VERSION, MIGRATIONS } from './migrations.js';
import type { PersistenceSink } from './persistence.js';

export async function readSchemaVersion(db: StoragePort): Promise<number> {
  const row = await db.get(`SELECT version FROM schema_version LIMIT 1`);
  const v = row?.['version'];
  return typeof v === 'number' ? v : 0;
}

/**
 * Bringt die Datenbank auf den aktuellen Stand.
 *
 * Es gibt keine Cloud-Kopie (docs/klausura/00). Eine fehlgeschlagene Migration
 * ist Datenverlust — deshalb: Snapshot vorher, Startverweigerung bei einer
 * unbekannt hohen Version, und kein Raten.
 */
export async function migrate(db: StoragePort, sink: PersistenceSink, snapshot: () => Uint8Array): Promise<void> {
  await db.run(`CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)`);
  const row = await db.get(`SELECT version FROM schema_version LIMIT 1`);
  if (row === undefined) {
    await db.run(`INSERT INTO schema_version (version) VALUES (0)`);
  }

  const current = await readSchemaVersion(db);

  if (current > LATEST_VERSION) {
    throw new Error(
      `Die Datenbank ist neuer als diese App: Schema ${current}, bekannt ist ${LATEST_VERSION}. ` +
        `Start verweigert, damit keine Daten verloren gehen.`,
    );
  }
  if (current === LATEST_VERSION) return;

  // Snapshot des Ausgangszustands, bevor irgendetwas verändert wird.
  await sink.saveBackup(current, snapshot());

  for (const m of MIGRATIONS) {
    if (m.version <= current) continue;
    await db.transaction(async () => {
      for (const stmt of m.statements) await db.run(stmt);
      await db.run(`UPDATE schema_version SET version = ?`, [m.version]);
    });
  }

  await db.persist();
}
