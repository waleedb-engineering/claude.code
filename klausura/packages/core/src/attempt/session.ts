import type { Attempt, AttemptId, AttemptMode, PointsTenths, TaskId } from '@klausura/model';
import type { ClockPort } from '@klausura/ports';
import { readElapsed, reanchorAfterRestart, startStopwatch, type StopwatchAnchors } from '../time/stopwatch.js';

export interface AttemptSession {
  readonly attempt: Attempt;
  readonly anchors: StopwatchAnchors;
}

export interface BeginAttemptInput {
  readonly id: AttemptId;
  readonly taskId: TaskId;
  readonly maxPoints: PointsTenths;
  readonly mode: AttemptMode;
}

export interface AnswerInput {
  readonly value: string;
  readonly unit: string;
}

export function beginAttempt(input: BeginAttemptInput, clock: ClockPort): AttemptSession {
  const anchors = startStopwatch(clock);
  return {
    anchors,
    attempt: {
      id: input.id,
      taskId: input.taskId,
      mode: input.mode,
      startedAtWall: anchors.startedAtWall,
      submittedAtWall: null,
      elapsedMs: 0,
      answerValue: null,
      answerUnit: null,
      awardedPoints: null,
      maxPoints: input.maxPoints,
    },
  };
}

/**
 * Setzt einen laufenden Versuch nach App-Neustart fort. Die Monotonzeit des
 * neuen Prozesses ist wertlos, also zählt die Wanduhr — `startedAtWall` kommt
 * aus der Datenbank.
 */
export function resumeAttempt(attempt: Attempt): AttemptSession {
  if (attempt.submittedAtWall !== null) {
    throw new Error(`Versuch ${attempt.id} ist bereits abgegeben und kann nicht fortgesetzt werden.`);
  }
  return { attempt, anchors: reanchorAfterRestart(attempt.startedAtWall) };
}

export function submitAttempt(
  session: AttemptSession,
  answer: AnswerInput | null,
  clock: ClockPort,
): Attempt {
  if (session.attempt.submittedAtWall !== null) {
    throw new Error(`Versuch ${session.attempt.id} wurde bereits abgegeben.`);
  }

  const reading = readElapsed(session.anchors, clock);
  const elapsedMs = reading.elapsedMs;

  // Wurde die Systemuhr während der Bearbeitung zurückgestellt, liegt die
  // rohe Wanduhr VOR dem Start — ein so gespeicherter Versuch verletzt
  // Invariante I16 ("Abgabe liegt vor dem Start"). Die verstrichene Zeit ist
  // in diesem Fall die glaubwürdigere Grösse (sie kommt aus der Monotonzeit),
  // also wird der Abgabezeitpunkt daraus rekonstruiert statt die gearbeitete
  // Zeit wegzuwerfen.
  const submittedAtWall = Math.max(clock.wall(), session.attempt.startedAtWall + elapsedMs);

  return {
    ...session.attempt,
    submittedAtWall,
    elapsedMs,
    answerValue: answer?.value ?? null,
    answerUnit: answer?.unit ?? null,
  };
}
