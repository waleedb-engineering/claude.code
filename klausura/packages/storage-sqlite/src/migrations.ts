/**
 * Migrationen als Code-Konstanten, nicht als .sql-Dateien.
 *
 * Grund: dieselben Migrationen laufen im Browser (sql.js), in Node (Tests) und
 * unter Tauri. Als Datei müsste jede dieser drei Umgebungen sie auf eigenem
 * Weg laden — als Modul lädt sie der Bundler überall gleich.
 *
 * Regeln (docs/klausura/08-architecture.md):
 * - Nur vorwärts. Nummern werden nie neu vergeben.
 * - Nie destruktiv ohne Backup-Pfad; der Migrator legt vorher einen Snapshot.
 * - Rohdaten sind unantastbar: Antworten, Zeiten und Korrekturen dürfen von
 *   einer Migration nicht verändert werden.
 */
export interface Migration {
  readonly version: number;
  readonly name: string;
  readonly statements: readonly string[];
}

export const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    name: 'initial',
    statements: [
      `CREATE TABLE subject (
         id TEXT PRIMARY KEY,
         name TEXT NOT NULL,
         code TEXT NOT NULL
       )`,
      `CREATE TABLE exam_paper (
         id TEXT PRIMARY KEY,
         subject_id TEXT NOT NULL REFERENCES subject(id),
         title TEXT NOT NULL,
         term TEXT NOT NULL,
         duration_minutes INTEGER NOT NULL,
         total_points INTEGER NOT NULL,
         pass_points INTEGER,
         status TEXT NOT NULL CHECK (status IN ('draft','ready')),
         imported_at INTEGER NOT NULL
       )`,
      `CREATE TABLE source_document (
         id TEXT PRIMARY KEY,
         exam_paper_id TEXT NOT NULL REFERENCES exam_paper(id),
         role TEXT NOT NULL CHECK (role IN ('exam','solution')),
         file_name TEXT NOT NULL,
         mime_type TEXT NOT NULL,
         sha256 TEXT NOT NULL,
         page_count INTEGER NOT NULL,
         has_text_layer INTEGER NOT NULL
       )`,
      `CREATE UNIQUE INDEX idx_source_document_sha ON source_document(sha256, exam_paper_id)`,
      `CREATE TABLE page_artifact (
         id TEXT PRIMARY KEY,
         source_document_id TEXT NOT NULL REFERENCES source_document(id),
         page_number INTEGER NOT NULL,
         width_pt REAL NOT NULL,
         height_pt REAL NOT NULL
       )`,
      `CREATE UNIQUE INDEX idx_page_artifact_page ON page_artifact(source_document_id, page_number)`,
      `CREATE TABLE task (
         id TEXT PRIMARY KEY,
         exam_paper_id TEXT NOT NULL REFERENCES exam_paper(id),
         ordinal TEXT NOT NULL,
         title TEXT NOT NULL,
         points INTEGER NOT NULL,
         time_budget_seconds INTEGER NOT NULL,
         kind TEXT NOT NULL,
         topic TEXT,
         page_artifact_id TEXT NOT NULL REFERENCES page_artifact(id),
         rect_x REAL NOT NULL, rect_y REAL NOT NULL,
         rect_w REAL NOT NULL, rect_h REAL NOT NULL
       )`,
      `CREATE INDEX idx_task_exam ON task(exam_paper_id)`,
      `CREATE TABLE segment_override (
         id TEXT PRIMARY KEY,
         page_artifact_id TEXT NOT NULL REFERENCES page_artifact(id),
         action TEXT NOT NULL,
         ordinal TEXT NOT NULL,
         points INTEGER NOT NULL,
         topic TEXT,
         rect_x REAL NOT NULL, rect_y REAL NOT NULL,
         rect_w REAL NOT NULL, rect_h REAL NOT NULL,
         created_at INTEGER NOT NULL
       )`,
      `CREATE INDEX idx_override_page ON segment_override(page_artifact_id)`,
      `CREATE TABLE attempt (
         id TEXT PRIMARY KEY,
         task_id TEXT NOT NULL REFERENCES task(id),
         mode TEXT NOT NULL CHECK (mode IN ('practice','simulation')),
         started_at_wall INTEGER NOT NULL,
         submitted_at_wall INTEGER,
         elapsed_ms INTEGER NOT NULL,
         answer_value TEXT,
         answer_unit TEXT,
         awarded_points INTEGER,
         max_points INTEGER NOT NULL
       )`,
      `CREATE INDEX idx_attempt_task ON attempt(task_id)`,
    ],
  },
];

export const LATEST_VERSION = MIGRATIONS.reduce((m, x) => Math.max(m, x.version), 0);
