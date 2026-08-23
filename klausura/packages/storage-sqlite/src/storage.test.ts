import { describe, expect, it } from 'vitest';
import { MemorySink } from './persistence.js';
import { openSqlJsStorage } from './adapter-sqljs.js';
import { LATEST_VERSION } from './migrations.js';
import { migrate, readSchemaVersion } from './migrator.js';

describe('Migrator', () => {
  it('bringt eine leere Datenbank auf die aktuelle Version', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    expect(await readSchemaVersion(db)).toBe(LATEST_VERSION);
    await db.close();
  });

  it('ist idempotent — zweites Oeffnen migriert nicht erneut', async () => {
    const sink = new MemorySink();
    const first = await openSqlJsStorage(sink);
    await first.run(`INSERT INTO subject (id,name,code) VALUES ('s1','Elektrotechnik 2','ET2')`);
    await first.persist();
    await first.close();

    const second = await openSqlJsStorage(sink);
    expect(await readSchemaVersion(second)).toBe(LATEST_VERSION);
    const row = await second.get(`SELECT name FROM subject WHERE id='s1'`);
    expect(row?.['name']).toBe('Elektrotechnik 2');
    await second.close();
  });

  it('legt vor einer Migration einen Snapshot an', async () => {
    const sink = new MemorySink();
    const db = await openSqlJsStorage(sink);
    await db.close();
    // Version 0 -> 1 muss einen Snapshot des Ausgangszustands hinterlassen.
    expect(await sink.listBackups()).toContain(0);
  });

  it('verweigert den Start bei einer neueren Schemaversion als bekannt', async () => {
    const sink = new MemorySink();
    const db = await openSqlJsStorage(sink);
    await db.run(`UPDATE schema_version SET version = ?`, [LATEST_VERSION + 5]);
    await db.persist();
    await db.close();

    await expect(openSqlJsStorage(sink)).rejects.toThrow(/neuer/i);
  });
});

describe('Migrator · Backup-Pflicht', () => {
  class NoBackupSink extends MemorySink {
    override readonly canBackup = false;
  }

  it('laesst eine rein additive Migration auch ohne Backup-Pfad zu', async () => {
    const db = await openSqlJsStorage(new NoBackupSink());
    expect(await readSchemaVersion(db)).toBe(LATEST_VERSION);
    await db.close();
  });

  it('verweigert eine destruktive Migration ohne Backup-Pfad', async () => {
    // Die Regel "nie destruktiv ohne Backup-Pfad" muss erzwungen sein, nicht
    // dokumentiert. Geprueft an einer kuenstlich als destruktiv markierten
    // Migration, damit der Schutz steht, BEVOR es eine echte gibt.
    const sink = new NoBackupSink();
    await expect(
      migrate(
        await openSqlJsStorage(sink),
        sink,
        () => new Uint8Array(),
        [{ version: LATEST_VERSION + 1, name: 'destruktiv', destructive: true, statements: ['DROP TABLE subject'] }],
      ),
    ).rejects.toThrow(/Snapshot|verweigert/i);
  });

  it('laesst dieselbe Migration mit Backup-Pfad zu', async () => {
    const sink = new MemorySink();
    const db = await openSqlJsStorage(sink);
    await migrate(db, sink, () => new Uint8Array(), [
      { version: LATEST_VERSION + 1, name: 'destruktiv', destructive: true, statements: ['DROP TABLE subject'] },
    ]);
    expect(await readSchemaVersion(db)).toBe(LATEST_VERSION + 1);
    await db.close();
  });
});

describe('StoragePort · Vertrag', () => {
  it('schreibt und liest Zeilen', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    await db.run(`INSERT INTO subject (id,name,code) VALUES (?,?,?)`, ['s1', 'ET2', 'ET2']);
    expect(await db.all(`SELECT * FROM subject`)).toHaveLength(1);
    await db.close();
  });

  it('gibt undefined zurueck, wenn nichts passt', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    expect(await db.get(`SELECT * FROM subject WHERE id='fehlt'`)).toBeUndefined();
    await db.close();
  });

  it('rollt eine fehlgeschlagene Transaktion zurueck', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    await expect(
      db.transaction(async () => {
        await db.run(`INSERT INTO subject (id,name,code) VALUES ('s1','A','A')`);
        throw new Error('absichtlich');
      }),
    ).rejects.toThrow('absichtlich');
    expect(await db.all(`SELECT * FROM subject`)).toHaveLength(0);
    await db.close();
  });

  it('behaelt eine erfolgreiche Transaktion', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    await db.transaction(async () => {
      await db.run(`INSERT INTO subject (id,name,code) VALUES ('s1','A','A')`);
    });
    expect(await db.all(`SELECT * FROM subject`)).toHaveLength(1);
    await db.close();
  });

  it('haelt NULL und Zahlen typrichtig', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    await db.run(`INSERT INTO subject (id,name,code) VALUES ('s1','A','A')`);
    await db.run(
      `INSERT INTO exam_paper (id,subject_id,title,term,duration_minutes,total_points,pass_points,status,imported_at)
       VALUES (?,?,?,?,?,?,?,?,?)`,
      ['e1', 's1', 'Klausur', 'WS23', 90, 900, null, 'draft', 1_700_000_000_000],
    );
    const row = await db.get(`SELECT pass_points, total_points FROM exam_paper WHERE id='e1'`);
    expect(row?.['pass_points']).toBeNull();
    expect(row?.['total_points']).toBe(900);
    await db.close();
  });

  const orphanInsert = `INSERT INTO exam_paper (id,subject_id,title,term,duration_minutes,total_points,pass_points,status,imported_at)
                        VALUES ('e1','gibt-es-nicht','K','WS23',90,900,NULL,'draft',1)`;

  it('erzwingt Fremdschluessel', async () => {
    const db = await openSqlJsStorage(new MemorySink());
    await expect(db.run(orphanInsert)).rejects.toThrow();
    await db.close();
  });

  it('erzwingt Fremdschluessel auch nach dem Speichern', async () => {
    // sql.js setzt PRAGMA foreign_keys beim export() auf 0 zurueck. Ohne
    // erneutes Setzen waere die referenzielle Integritaet nach dem ersten
    // persist() still abgeschaltet — ein Fehler, der erst in Produktion
    // auffiele.
    const db = await openSqlJsStorage(new MemorySink());
    await db.persist();
    await expect(db.run(orphanInsert)).rejects.toThrow();
    await db.close();
  });

  it('erzwingt Fremdschluessel auch nach einem Neustart', async () => {
    const sink = new MemorySink();
    const first = await openSqlJsStorage(sink);
    await first.close();
    const second = await openSqlJsStorage(sink);
    await expect(second.run(orphanInsert)).rejects.toThrow();
    await second.close();
  });
});
