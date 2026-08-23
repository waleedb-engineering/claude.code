import { beforeEach, describe, expect, it } from 'vitest';
import { MemorySink, type PersistenceSink } from './persistence.js';
import { openSqlJsStorage } from './adapter-sqljs.js';
import {
  findRunningAttempt, insertExamPaper, insertOverride, insertPageArtifact,
  insertSourceDocument, listAttempts, listOverrides, listTasks, replaceTasks,
  saveAttempt, upsertSubject,
} from './repositories.js';
import {
  asAttemptId, asExamPaperId, asPageArtifactId, asSegmentOverrideId,
  asSourceDocumentId, asSubjectId, asTaskId,
} from '@klausura/model';
import type { StoragePort } from '@klausura/ports';

const subjectId = asSubjectId('s1');
const examId = asExamPaperId('e1');
const docId = asSourceDocumentId('d1');
const pageId = asPageArtifactId('p1');
const rect = { x: 0.1, y: 0.1, width: 0.5, height: 0.2 };

async function seed(sink: PersistenceSink): Promise<StoragePort> {
  const db = await openSqlJsStorage(sink);
  await upsertSubject(db, { id: subjectId, name: 'Elektrotechnik 2', code: 'ET2' });
  await insertExamPaper(db, {
    id: examId, subjectId, title: 'Altklausur 03', term: 'WS 2023',
    durationMinutes: 90, totalPoints: 900, passPoints: 450,
    status: 'draft', importedAt: 1_700_000_000_000,
  });
  await insertSourceDocument(db, {
    id: docId, examPaperId: examId, role: 'exam', fileName: 'et2.pdf',
    mimeType: 'application/pdf', sha256: 'abc', pageCount: 1, hasTextLayer: true,
  });
  await insertPageArtifact(db, { id: pageId, sourceDocumentId: docId, pageNumber: 1, widthPt: 595, heightPt: 842 });
  return db;
}

const task = (ordinal: string, points: number) => ({
  id: asTaskId(`${examId}:${ordinal}`), examPaperId: examId, ordinal,
  title: `Aufgabe ${ordinal}`, points, timeBudgetSeconds: 600,
  kind: 'calculation' as const, topic: null, pageArtifactId: pageId, rect,
});

describe('Aufgaben', () => {
  let db: StoragePort;
  beforeEach(async () => { db = await seed(new MemorySink()); });

  it('legt Aufgaben an und liest sie nach Nummer sortiert', async () => {
    await replaceTasks(db, examId, [task('A10', 100), task('A2', 200)]);
    expect((await listTasks(db, examId)).map((t) => t.ordinal)).toEqual(['A2', 'A10']);
  });

  it('aktualisiert eine bestehende Aufgabe statt sie zu verdoppeln', async () => {
    await replaceTasks(db, examId, [task('A1', 100)]);
    await replaceTasks(db, examId, [task('A1', 850)]);
    const tasks = await listTasks(db, examId);
    expect(tasks).toHaveLength(1);
    expect(tasks[0]?.points).toBe(850);
  });

  it('entfernt eine Aufgabe, die aus der Zerlegung verschwindet', async () => {
    await replaceTasks(db, examId, [task('A1', 100), task('A2', 100)]);
    await replaceTasks(db, examId, [task('A1', 100)]);
    expect(await listTasks(db, examId)).toHaveLength(1);
  });

  it('loescht niemals eine Aufgabe, an der ein Versuch haengt', async () => {
    await replaceTasks(db, examId, [task('A1', 100)]);
    await saveAttempt(db, {
      id: asAttemptId('a1'), taskId: task('A1', 100).id, mode: 'practice',
      startedAtWall: 1_000, submittedAtWall: 2_000, elapsedMs: 1_000,
      answerValue: '12', answerUnit: 'kΩ', awardedPoints: null, maxPoints: 100,
    });
    await replaceTasks(db, examId, []); // Nutzer verwirft die Markierung
    expect(await listTasks(db, examId)).toHaveLength(1);
  });
});

describe('Korrekturen', () => {
  it('speichert Korrekturen und liest sie je Seite', async () => {
    const db = await seed(new MemorySink());
    await insertOverride(db, {
      id: asSegmentOverrideId('o1'), pageArtifactId: pageId, action: 'create',
      ordinal: 'A1', points: 850, rect, createdAt: 5,
    });
    const out = await listOverrides(db, [pageId]);
    expect(out).toHaveLength(1);
    expect(out[0]?.points).toBe(850);
    expect(out[0]?.rect).toEqual(rect);
  });

  it('gibt eine leere Liste ohne Seiten zurueck', async () => {
    expect(await listOverrides(await seed(new MemorySink()), [])).toEqual([]);
  });
});

describe('Versuche', () => {
  it('findet einen laufenden Versuch und ignoriert abgegebene', async () => {
    const db = await seed(new MemorySink());
    const t = task('A1', 850);
    await replaceTasks(db, examId, [t]);
    await saveAttempt(db, {
      id: asAttemptId('a-done'), taskId: t.id, mode: 'practice',
      startedAtWall: 1_000, submittedAtWall: 2_000, elapsedMs: 1_000,
      answerValue: null, answerUnit: null, awardedPoints: null, maxPoints: 850,
    });
    expect(await findRunningAttempt(db, t.id)).toBeUndefined();

    await saveAttempt(db, {
      id: asAttemptId('a-live'), taskId: t.id, mode: 'practice',
      startedAtWall: 3_000, submittedAtWall: null, elapsedMs: 0,
      answerValue: null, answerUnit: null, awardedPoints: null, maxPoints: 850,
    });
    expect((await findRunningAttempt(db, t.id))?.id).toBe('a-live');
  });

  it('ueberlebt einen App-Neustart', async () => {
    const sink = new MemorySink();
    const first = await seed(sink);
    const t = task('A1', 850);
    await replaceTasks(first, examId, [t]);
    await saveAttempt(first, {
      id: asAttemptId('a1'), taskId: t.id, mode: 'practice',
      startedAtWall: 1_700_000_000_000, submittedAtWall: 1_700_000_360_000,
      elapsedMs: 360_000, answerValue: '12', answerUnit: 'kΩ',
      awardedPoints: null, maxPoints: 850,
    });
    await first.close();

    // Neue Datenbankinstanz aus derselben Ablage — genau das macht ein Neustart.
    const second = await openSqlJsStorage(sink);
    const attempts = await listAttempts(second, t.id);
    expect(attempts).toHaveLength(1);
    expect(attempts[0]?.answerValue).toBe('12');
    expect(attempts[0]?.answerUnit).toBe('kΩ');
    expect(attempts[0]?.elapsedMs).toBe(360_000);
    await second.close();
  });
});
