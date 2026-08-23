import type {
  AttemptId, ExamPaperId, PageArtifactId, SegmentOverrideId,
  SourceDocumentId, SubjectId, SubtaskId, TaskId,
} from './ids.js';
import type { PointsTenths } from './points.js';

/** Zeitpunkt als Millisekunden seit Epoche (Wanduhr). */
export type EpochMs = number;

/**
 * Rechteck in NORMALISIERTEN Seitenkoordinaten, 0…1 relativ zur Seite.
 * Bewusst nicht in Pixeln: Zoomstufe, Bildschirmdichte und Renderauflösung
 * dürfen die gespeicherte Markierung nicht verändern.
 */
export interface NormRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface Subject {
  readonly id: SubjectId;
  readonly name: string;
  readonly code: string;
}

export interface ExamPaper {
  readonly id: ExamPaperId;
  readonly subjectId: SubjectId;
  readonly title: string;
  readonly term: string;
  readonly durationMinutes: number;
  readonly totalPoints: PointsTenths;
  readonly passPoints: PointsTenths | null;
  readonly status: 'draft' | 'ready';
  readonly importedAt: EpochMs;
}

export type SourceRole = 'exam' | 'solution';

export interface SourceDocument {
  readonly id: SourceDocumentId;
  readonly examPaperId: ExamPaperId;
  readonly role: SourceRole;
  readonly fileName: string;
  readonly mimeType: string;
  readonly sha256: string;
  readonly pageCount: number;
  readonly hasTextLayer: boolean;
}

export interface PageArtifact {
  readonly id: PageArtifactId;
  readonly sourceDocumentId: SourceDocumentId;
  readonly pageNumber: number;
  readonly widthPt: number;
  readonly heightPt: number;
}

export type TaskKind = 'calculation' | 'derivation' | 'design' | 'text';

export interface Task {
  readonly id: TaskId;
  readonly examPaperId: ExamPaperId;
  readonly ordinal: string;
  readonly title: string;
  readonly points: PointsTenths;
  readonly timeBudgetSeconds: number;
  readonly kind: TaskKind;
  readonly topic: string | null;
  readonly pageArtifactId: PageArtifactId;
  readonly rect: NormRect;
}

export interface Subtask {
  readonly id: SubtaskId;
  readonly taskId: TaskId;
  readonly ordinal: string;
  readonly points: PointsTenths;
}

export type SegmentAction = 'create' | 'adjust' | 'split' | 'merge' | 'reject';

/**
 * Eine Nutzerkorrektur. Sie ist ein eigenes Faktum, kein Ergebnis:
 * ein erneuter Automatiklauf darf sie nie überschreiben (Invariante I12).
 */
export interface SegmentOverride {
  readonly id: SegmentOverrideId;
  readonly pageArtifactId: PageArtifactId;
  readonly action: SegmentAction;
  readonly ordinal: string;
  readonly points: PointsTenths;
  readonly rect: NormRect;
  readonly createdAt: EpochMs;
}

export type AttemptMode = 'practice' | 'simulation';

export interface Attempt {
  readonly id: AttemptId;
  readonly taskId: TaskId;
  readonly mode: AttemptMode;
  readonly startedAtWall: EpochMs;
  readonly submittedAtWall: EpochMs | null;
  readonly elapsedMs: number;
  readonly answerValue: string | null;
  readonly answerUnit: string | null;
  readonly awardedPoints: PointsTenths | null;
  readonly maxPoints: PointsTenths;
}
