import type { Attempt, NormRect, Subtask, Task } from './entities.js';
import { formatPoints, type PointsTenths } from './points.js';

/**
 * Invarianten aus docs/klausura/02-domain-model.md.
 *
 * Sie WERFEN NICHT. Sie geben Verletzungen als Liste zurück, weil die
 * Segmentierungs-UI dem Nutzer alle Abweichungen gleichzeitig zeigen muss —
 * die Punktesummen-Kreuzprobe ist dort ein Diagnosewerkzeug, kein Absturz.
 *
 * Wer eine Verletzung in einem Pfad findet, in dem sie nicht vorkommen darf,
 * behandelt sie als unerwarteten Fehler (docs/klausura/08, Fehlerklassen).
 */
export interface InvariantViolation {
  readonly code: 'I1' | 'I2' | 'I4' | 'I5' | 'I11' | 'I16';
  readonly message: string;
}

const violation = (code: InvariantViolation['code'], message: string): InvariantViolation[] => [{ code, message }];

const sumPoints = (items: readonly { readonly points: PointsTenths }[]): PointsTenths =>
  items.reduce((acc, i) => acc + i.points, 0);

/** I1 — Hat eine Aufgabe Teilaufgaben, ergeben deren Punkte die Aufgabenpunkte. */
export function checkSubtaskPointSum(task: Task, subtasks: readonly Subtask[]): InvariantViolation[] {
  if (subtasks.length === 0) return [];
  const sum = sumPoints(subtasks);
  if (sum === task.points) return [];
  return violation(
    'I1',
    `Aufgabe ${task.ordinal}: Teilaufgaben ergeben ${formatPoints(sum)} P, die Aufgabe nennt ${formatPoints(task.points)} P.`,
  );
}

/** I2 — Die Aufgabenpunkte ergeben die Gesamtpunktzahl der Klausur. */
export function checkExamPointSum(totalPoints: PointsTenths, tasks: readonly Task[]): InvariantViolation[] {
  const sum = sumPoints(tasks);
  if (sum === totalPoints) return [];
  const diff = sum - totalPoints;
  const direction = diff < 0 ? 'fehlen' : 'zu viel';
  return violation(
    'I2',
    `Aufgaben ergeben ${formatPoints(sum)} P gegen ${formatPoints(totalPoints)} P der Klausur — ${formatPoints(Math.abs(diff))} P ${direction}.`,
  );
}

/** I4 — Erreichte Punkte liegen zwischen null und dem Maximum der Aufgabe. */
export function checkAttemptPoints(attempt: Attempt): InvariantViolation[] {
  const awarded = attempt.awardedPoints;
  if (awarded === null) return [];
  if (awarded < 0) return violation('I4', `Versuch ${attempt.id}: ${formatPoints(awarded)} P ist negativ.`);
  if (awarded > attempt.maxPoints) {
    return violation(
      'I4',
      `Versuch ${attempt.id}: ${formatPoints(awarded)} P über dem Maximum von ${formatPoints(attempt.maxPoints)} P.`,
    );
  }
  return [];
}

/** I5 — Die Zeitbudgets der Aufgaben passen in die Klausurdauer. */
export function checkTimeBudgetSum(durationMinutes: number, tasks: readonly Task[]): InvariantViolation[] {
  const sum = tasks.reduce((acc, t) => acc + t.timeBudgetSeconds, 0);
  const available = durationMinutes * 60;
  if (sum <= available) return [];
  return violation(
    'I5',
    `Zeitbudgets ergeben ${sum} s, die Klausur dauert ${available} s.`,
  );
}

/** I11 — Eine Markierung liegt vollständig auf der Seite und hat Ausdehnung. */
export function checkRectWithinPage(rect: NormRect): InvariantViolation[] {
  if (rect.width <= 0 || rect.height <= 0) {
    return violation('I11', 'Markierung ohne Ausdehnung.');
  }
  const withinBounds =
    rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= 1 && rect.y + rect.height <= 1;
  if (withinBounds) return [];
  return violation(
    'I11',
    `Markierung liegt ausserhalb der Seite (x ${rect.x}, y ${rect.y}, b ${rect.width}, h ${rect.height}).`,
  );
}

/**
 * I16 — Die Zeitachse eines Versuchs ist widerspruchsfrei.
 *
 * Die Obergrenze ist der Punkt, an dem ein falsch gerechneter Timer auffliegt:
 * verstrichene Zeit kann nie länger sein als die Spanne zwischen Start und
 * Abgabe auf der Wanduhr. Standby verkürzt sie höchstens, verlängert sie nie.
 */
export function checkAttemptTimeline(attempt: Attempt): InvariantViolation[] {
  const out: InvariantViolation[] = [];
  if (attempt.elapsedMs < 0) {
    out.push({ code: 'I16', message: `Versuch ${attempt.id}: verstrichene Zeit ist negativ.` });
  }
  const submitted = attempt.submittedAtWall;
  if (submitted !== null) {
    if (submitted < attempt.startedAtWall) {
      out.push({ code: 'I16', message: `Versuch ${attempt.id}: Abgabe liegt vor dem Start.` });
    } else if (attempt.elapsedMs > submitted - attempt.startedAtWall) {
      out.push({
        code: 'I16',
        message: `Versuch ${attempt.id}: verstrichene Zeit ${attempt.elapsedMs} ms übersteigt das Zeitfenster ${submitted - attempt.startedAtWall} ms.`,
      });
    }
  }
  return out;
}
