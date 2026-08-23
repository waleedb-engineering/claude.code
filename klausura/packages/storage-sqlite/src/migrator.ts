import type { StoragePort } from '@klausura/ports';
import { MIGRATIONS, type Migration } from './migrations.js';
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
/**
 * `snapshot` darf asynchron sein: sql.js liefert die Bytes synchron,
 * expo-sqlite ueber serializeAsync. Der Migrator kennt den Unterschied nicht.
 */
export type SnapshotFn = () => Uint8Array | Promise<Uint8Array>;

export async function migrate(
  db: StoragePort,
  sink: PersistenceSink,
  snapshot: SnapshotFn,
  /** Injizierbar, damit der Schutz gegen destruktive Migrationen pruefbar ist. */
  migrations: readonly Migration[] = MIGRATIONS,
): Promise<void> {
  await db.run(`CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)`);
  const row = await db.get(`SELECT version FROM schema_version LIMIT 1`);
  if (row === undefined) {
    await db.run(`INSERT INTO schema_version (version) VALUES (0)`);
  }

  const latest = migrations.reduce((m, x) => Math.max(m, x.version), 0);
  const current = await readSchemaVersion(db);

  if (current > latest) {
    throw new Error(
      `Die Datenbank ist neuer als diese App: Schema ${current}, bekannt ist ${latest}. ` +
        `Start verweigert, damit keine Daten verloren gehen.`,
    );
  }
  if (current === latest) return;

  const pending = migrations.filter((m) => m.version > current);

  // "Nie destruktiv ohne Backup-Pfad" — hier erzwungen, nicht nur zugesagt.
  const risky = pending.filter((m) => m.destructive);
  if (risky.length > 0 && !sink.canBackup) {
    throw new Error(
      `Migration ${risky.map((m) => m.version).join(', ')} verändert bestehende Daten, ` +
        `aber diese Ablage kann keinen Snapshot aufbewahren. Start verweigert.`,
    );
  }

  if (sink.canBackup) {
    // Snapshot des Ausgangszustands, bevor irgendetwas verändert wird.
    await sink.saveBackup(current, await snapshot());
  }

  for (const m of pending) {
    await db.transaction(async () => {
      for (const stmt of m.statements) await db.run(stmt);
      await db.run(`UPDATE schema_version SET version = ?`, [m.version]);
    });
  }

  await db.persist();
}
