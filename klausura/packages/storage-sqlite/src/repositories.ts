import {
  asAttemptId, asExamPaperId, asPageArtifactId, asSourceDocumentId,
  asSubjectId, asTaskId,
} from '@klausura/model';
import type {
  Attempt, AttemptId, ExamPaper, ExamPaperId, NormRect, PageArtifact,
  PageArtifactId, SegmentOverride, SourceDocument, SourceDocumentId,
  Subject, Task, TaskKind,
} from '@klausura/model';
import type { Row, SqlValue, StoragePort } from '@klausura/ports';

/**
 * Die einzige Stelle mit SQL-Strings. Alles darüber arbeitet mit Entitäten.
 * Die Umwandlung snake_case ↔ camelCase passiert hier und nirgends sonst.
 */

const str = (row: Row, key: string): string => {
  const v = row[key];
  if (typeof v !== 'string') throw new Error(`Spalte ${key}: Text erwartet, ${typeof v} bekommen.`);
  return v;
};
const num = (row: Row, key: string): number => {
  const v = row[key];
  if (typeof v !== 'number') throw new Error(`Spalte ${key}: Zahl erwartet, ${typeof v} bekommen.`);
  return v;
};
const numOrNull = (row: Row, key: string): number | null => {
  const v = row[key];
  return typeof v === 'number' ? v : null;
};
const strOrNull = (row: Row, key: string): string | null => {
  const v = row[key];
  return typeof v === 'string' ? v : null;
};
const rectOf = (row: Row): NormRect => ({
  x: num(row, 'rect_x'), y: num(row, 'rect_y'),
  width: num(row, 'rect_w'), height: num(row, 'rect_h'),
});

// ---------------------------------------------------------------- Subject

export async function upsertSubject(db: StoragePort, s: Subject): Promise<void> {
  await db.run(
    `INSERT INTO subject (id,name,code) VALUES (?,?,?)
     ON CONFLICT(id) DO UPDATE SET name=excluded.name, code=excluded.code`,
    [s.id, s.name, s.code],
  );
}

export async function listSubjects(db: StoragePort): Promise<Subject[]> {
  const rows = await db.all(`SELECT * FROM subject ORDER BY name`);
  return rows.map((r) => ({ id: asSubjectId(str(r, 'id')), name: str(r, 'name'), code: str(r, 'code') }));
}

// -------------------------------------------------------------- ExamPaper

const toExamPaper = (r: Row): ExamPaper => ({
  id: asExamPaperId(str(r, 'id')),
  subjectId: asSubjectId(str(r, 'subject_id')),
  title: str(r, 'title'),
  term: str(r, 'term'),
  durationMinutes: num(r, 'duration_minutes'),
  totalPoints: num(r, 'total_points'),
  passPoints: numOrNull(r, 'pass_points'),
  status: str(r, 'status') === 'ready' ? 'ready' : 'draft',
  importedAt: num(r, 'imported_at'),
});

export async function insertExamPaper(db: StoragePort, e: ExamPaper): Promise<void> {
  await db.run(
    `INSERT INTO exam_paper
       (id,subject_id,title,term,duration_minutes,total_points,pass_points,status,imported_at)
     VALUES (?,?,?,?,?,?,?,?,?)`,
    [e.id, e.subjectId, e.title, e.term, e.durationMinutes, e.totalPoints, e.passPoints, e.status, e.importedAt],
  );
}

export async function setExamPaperStatus(db: StoragePort, id: ExamPaperId, status: ExamPaper['status']): Promise<void> {
  await db.run(`UPDATE exam_paper SET status=? WHERE id=?`, [status, id]);
}

export async function listExamPapers(db: StoragePort): Promise<ExamPaper[]> {
  return (await db.all(`SELECT * FROM exam_paper ORDER BY imported_at DESC`)).map(toExamPaper);
}

export async function getExamPaper(db: StoragePort, id: ExamPaperId): Promise<ExamPaper | undefined> {
  const r = await db.get(`SELECT * FROM exam_paper WHERE id=?`, [id]);
  return r === undefined ? undefined : toExamPaper(r);
}

// --------------------------------------------------------- SourceDocument

export async function insertSourceDocument(db: StoragePort, d: SourceDocument): Promise<void> {
  await db.run(
    `INSERT INTO source_document (id,exam_paper_id,role,file_name,mime_type,sha256,page_count,has_text_layer)
     VALUES (?,?,?,?,?,?,?,?)`,
    [d.id, d.examPaperId, d.role, d.fileName, d.mimeType, d.sha256, d.pageCount, d.hasTextLayer ? 1 : 0],
  );
}

export async function findDocumentBySha(db: StoragePort, sha256: string): Promise<SourceDocument | undefined> {
  const r = await db.get(`SELECT * FROM source_document WHERE sha256=? LIMIT 1`, [sha256]);
  if (r === undefined) return undefined;
  return {
    id: asSourceDocumentId(str(r, 'id')),
    examPaperId: asExamPaperId(str(r, 'exam_paper_id')),
    role: str(r, 'role') === 'solution' ? 'solution' : 'exam',
    fileName: str(r, 'file_name'),
    mimeType: str(r, 'mime_type'),
    sha256: str(r, 'sha256'),
    pageCount: num(r, 'page_count'),
    hasTextLayer: num(r, 'has_text_layer') === 1,
  };
}

// ----------------------------------------------------------- PageArtifact

export async function insertPageArtifact(db: StoragePort, p: PageArtifact): Promise<void> {
  await db.run(
    `INSERT INTO page_artifact (id,source_document_id,page_number,width_pt,height_pt) VALUES (?,?,?,?,?)`,
    [p.id, p.sourceDocumentId, p.pageNumber, p.widthPt, p.heightPt],
  );
}

export async function listPageArtifacts(db: StoragePort, docId: SourceDocumentId): Promise<PageArtifact[]> {
  const rows = await db.all(`SELECT * FROM page_artifact WHERE source_document_id=? ORDER BY page_number`, [docId]);
  return rows.map((r) => ({
    id: asPageArtifactId(str(r, 'id')),
    sourceDocumentId: asSourceDocumentId(str(r, 'source_document_id')),
    pageNumber: num(r, 'page_number'),
    widthPt: num(r, 'width_pt'),
    heightPt: num(r, 'height_pt'),
  }));
}

// ------------------------------------------------------------------ Task

const toTask = (r: Row): Task => ({
  id: asTaskId(str(r, 'id')),
  examPaperId: asExamPaperId(str(r, 'exam_paper_id')),
  ordinal: str(r, 'ordinal'),
  title: str(r, 'title'),
  points: num(r, 'points'),
  timeBudgetSeconds: num(r, 'time_budget_seconds'),
  kind: str(r, 'kind') as TaskKind,
  topic: strOrNull(r, 'topic'),
  pageArtifactId: asPageArtifactId(str(r, 'page_artifact_id')),
  rect: rectOf(r),
});

export async function replaceTasks(db: StoragePort, examPaperId: ExamPaperId, tasks: readonly Task[]): Promise<void> {
  await db.transaction(async () => {
    // Aufgaben werden aus Korrekturen neu abgeleitet. Versuche haengen an
    // Aufgaben-IDs, deshalb bleiben bestehende IDs stabil (die UI vergibt sie
    // aus der Aufgabennummer) und nur Verwaiste verschwinden.
    const keep = new Set(tasks.map((t) => t.id as string));
    const existing = await db.all(`SELECT id FROM task WHERE exam_paper_id=?`, [examPaperId]);
    for (const row of existing) {
      const id = str(row, 'id');
      if (keep.has(id)) continue;
      const used = await db.get(`SELECT 1 AS n FROM attempt WHERE task_id=? LIMIT 1`, [id]);
      if (used !== undefined) continue; // Aufgabe mit Versuchen wird nie geloescht.
      await db.run(`DELETE FROM task WHERE id=?`, [id]);
    }
    for (const t of tasks) {
      await db.run(
        `INSERT INTO task (id,exam_paper_id,ordinal,title,points,time_budget_seconds,kind,topic,page_artifact_id,rect_x,rect_y,rect_w,rect_h)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET
           ordinal=excluded.ordinal, title=excluded.title, points=excluded.points,
           time_budget_seconds=excluded.time_budget_seconds, kind=excluded.kind, topic=excluded.topic,
           page_artifact_id=excluded.page_artifact_id,
           rect_x=excluded.rect_x, rect_y=excluded.rect_y, rect_w=excluded.rect_w, rect_h=excluded.rect_h`,
        [t.id, t.examPaperId, t.ordinal, t.title, t.points, t.timeBudgetSeconds, t.kind, t.topic,
         t.pageArtifactId, t.rect.x, t.rect.y, t.rect.width, t.rect.height],
      );
    }
  });
}

export async function listTasks(db: StoragePort, examPaperId: ExamPaperId): Promise<Task[]> {
  const rows = await db.all(`SELECT * FROM task WHERE exam_paper_id=?`, [examPaperId]);
  return rows.map(toTask).sort((a, b) => a.ordinal.localeCompare(b.ordinal, 'de', { numeric: true }));
}

export async function getTask(db: StoragePort, id: string): Promise<Task | undefined> {
  const r = await db.get(`SELECT * FROM task WHERE id=?`, [id]);
  return r === undefined ? undefined : toTask(r);
}

// -------------------------------------------------------- SegmentOverride

export async function insertOverride(db: StoragePort, o: SegmentOverride): Promise<void> {
  await db.run(
    `INSERT INTO segment_override (id,page_artifact_id,action,ordinal,points,topic,rect_x,rect_y,rect_w,rect_h,created_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
    [o.id, o.pageArtifactId, o.action, o.ordinal, o.points, o.topic,
     o.rect.x, o.rect.y, o.rect.width, o.rect.height, o.createdAt],
  );
}

export async function listOverrides(db: StoragePort, pageIds: readonly PageArtifactId[]): Promise<SegmentOverride[]> {
  if (pageIds.length === 0) return [];
  const marks = pageIds.map(() => '?').join(',');
  const rows = await db.all(
    `SELECT * FROM segment_override WHERE page_artifact_id IN (${marks}) ORDER BY created_at`,
    pageIds as readonly SqlValue[],
  );
  return rows.map((r) => ({
    id: str(r, 'id') as SegmentOverride['id'],
    pageArtifactId: asPageArtifactId(str(r, 'page_artifact_id')),
    action: str(r, 'action') as SegmentOverride['action'],
    ordinal: str(r, 'ordinal'),
    points: num(r, 'points'),
    topic: strOrNull(r, 'topic'),
    rect: rectOf(r),
    createdAt: num(r, 'created_at'),
  }));
}

// --------------------------------------------------------------- Attempt

const toAttempt = (r: Row): Attempt => ({
  id: asAttemptId(str(r, 'id')),
  taskId: asTaskId(str(r, 'task_id')),
  mode: str(r, 'mode') === 'simulation' ? 'simulation' : 'practice',
  startedAtWall: num(r, 'started_at_wall'),
  submittedAtWall: numOrNull(r, 'submitted_at_wall'),
  elapsedMs: num(r, 'elapsed_ms'),
  answerValue: strOrNull(r, 'answer_value'),
  answerUnit: strOrNull(r, 'answer_unit'),
  awardedPoints: numOrNull(r, 'awarded_points'),
  maxPoints: num(r, 'max_points'),
});

export async function saveAttempt(db: StoragePort, a: Attempt): Promise<void> {
  await db.run(
    `INSERT INTO attempt (id,task_id,mode,started_at_wall,submitted_at_wall,elapsed_ms,answer_value,answer_unit,awarded_points,max_points)
     VALUES (?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(id) DO UPDATE SET
       submitted_at_wall=excluded.submitted_at_wall, elapsed_ms=excluded.elapsed_ms,
       answer_value=excluded.answer_value, answer_unit=excluded.answer_unit,
       awarded_points=excluded.awarded_points`,
    [a.id, a.taskId, a.mode, a.startedAtWall, a.submittedAtWall, a.elapsedMs,
     a.answerValue, a.answerUnit, a.awardedPoints, a.maxPoints],
  );
}

export async function listAttempts(db: StoragePort, taskId: string): Promise<Attempt[]> {
  const rows = await db.all(`SELECT * FROM attempt WHERE task_id=? ORDER BY started_at_wall DESC`, [taskId]);
  return rows.map(toAttempt);
}

/** Ein laufender Versuch — der Fall, den ein App-Neustart fortsetzen muss. */
export async function findRunningAttempt(db: StoragePort, taskId: string): Promise<Attempt | undefined> {
  const r = await db.get(
    `SELECT * FROM attempt WHERE task_id=? AND submitted_at_wall IS NULL ORDER BY started_at_wall DESC LIMIT 1`,
    [taskId],
  );
  return r === undefined ? undefined : toAttempt(r);
}

export async function getAttempt(db: StoragePort, id: AttemptId): Promise<Attempt | undefined> {
  const r = await db.get(`SELECT * FROM attempt WHERE id=?`, [id]);
  return r === undefined ? undefined : toAttempt(r);
}
