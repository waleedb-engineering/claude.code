/**
 * Getypte IDs. Verhindert, dass eine TaskId dort landet, wo eine AttemptId
 * erwartet wird — der Compiler fängt es, nicht der Test.
 */
declare const brand: unique symbol;
type Branded<T, B extends string> = T & { readonly [brand]: B };

export type SubjectId = Branded<string, 'SubjectId'>;
export type ExamPaperId = Branded<string, 'ExamPaperId'>;
export type SourceDocumentId = Branded<string, 'SourceDocumentId'>;
export type PageArtifactId = Branded<string, 'PageArtifactId'>;
export type TaskId = Branded<string, 'TaskId'>;
export type SubtaskId = Branded<string, 'SubtaskId'>;
export type SegmentOverrideId = Branded<string, 'SegmentOverrideId'>;
export type AttemptId = Branded<string, 'AttemptId'>;

export const asSubjectId = (v: string): SubjectId => v as SubjectId;
export const asExamPaperId = (v: string): ExamPaperId => v as ExamPaperId;
export const asSourceDocumentId = (v: string): SourceDocumentId => v as SourceDocumentId;
export const asPageArtifactId = (v: string): PageArtifactId => v as PageArtifactId;
export const asTaskId = (v: string): TaskId => v as TaskId;
export const asSubtaskId = (v: string): SubtaskId => v as SubtaskId;
export const asSegmentOverrideId = (v: string): SegmentOverrideId => v as SegmentOverrideId;
export const asAttemptId = (v: string): AttemptId => v as AttemptId;
