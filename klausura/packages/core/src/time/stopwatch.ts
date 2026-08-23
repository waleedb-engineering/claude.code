import type { ClockPort } from '@klausura/ports';

/**
 * Der Timer ist sicherheitskritisch: er trägt das Produktversprechen
 * "unter Zeitdruck". Zwei Regeln machen ihn belastbar.
 *
 * 1. NIE AKKUMULIEREN. Verstrichene Zeit wird bei jedem Aufruf aus
 *    Zeitstempeln gerechnet. Damit ist Drift konstruktiv ausgeschlossen,
 *    nicht nur klein gehalten. `setInterval` addiert Fehler; das hier nicht.
 *
 * 2. ZWEI UHREN GLEICHZEITIG. Die Wanduhr überlebt Standby und Neustart,
 *    lässt sich aber verstellen. Die Monotonzeit lässt sich nicht verstellen,
 *    verliert aber beim Neustart ihren Bezug. Keine allein genügt.
 */

/** Toleranz, unterhalb derer eine Abweichung beider Uhren als Rauschen gilt. */
const DRIFT_TOLERANCE_MS = 2_000;

export interface StopwatchAnchors {
  readonly startedAtWall: number;
  /**
   * `null` nach einem Prozessneustart: die Monotonzeit des neuen Prozesses
   * hat keinen Bezug zum alten Startpunkt und ist damit wertlos.
   */
  readonly startedAtMono: number | null;
}

export type ElapsedSource = 'monotonic' | 'wall';

export type ElapsedAnomaly =
  | 'none'
  /** Wanduhr weiter voraus als die Monotonzeit: Gerät schlief, oder die Uhr sprang vor. */
  | 'device-slept'
  /** Wanduhr hinter der Monotonzeit: Systemzeit wurde zurückgestellt. */
  | 'wall-clock-back';

export interface ElapsedReading {
  readonly elapsedMs: number;
  readonly source: ElapsedSource;
  readonly anomaly: ElapsedAnomaly;
}

export function startStopwatch(clock: ClockPort): StopwatchAnchors {
  return { startedAtWall: clock.wall(), startedAtMono: clock.mono() };
}

/**
 * Nach einem Neustart liegt nur noch `startedAtWall` vor — es kommt aus der
 * Datenbank. Der laufende Versuch wird auf der Wanduhr fortgesetzt.
 */
export function reanchorAfterRestart(startedAtWall: number): StopwatchAnchors {
  return { startedAtWall, startedAtMono: null };
}

export function readElapsed(anchors: StopwatchAnchors, clock: ClockPort): ElapsedReading {
  const wallDelta = clock.wall() - anchors.startedAtWall;

  if (anchors.startedAtMono === null) {
    return { elapsedMs: Math.max(0, wallDelta), source: 'wall', anomaly: 'none' };
  }

  const monoDelta = clock.mono() - anchors.startedAtMono;
  const drift = wallDelta - monoDelta;

  if (drift > DRIFT_TOLERANCE_MS) {
    // Standby oder Vorwärtssprung. Von aussen nicht unterscheidbar — und in
    // beiden Fällen ist die Wanduhr das ehrlichere Mass: bei Standby ist die
    // Zeit wirklich vergangen, bei einer NTP-Korrektur war die Monotonzeit
    // ohnehin nur relativ.
    return { elapsedMs: Math.max(0, wallDelta), source: 'wall', anomaly: 'device-slept' };
  }

  if (drift < -DRIFT_TOLERANCE_MS) {
    // Systemzeit zurückgestellt. Die Monotonzeit gewinnt — sonst liesse sich
    // durch Verstellen der Uhr Prüfungszeit gewinnen. Nicht auf die Wanduhr
    // begrenzen: sie ist hier gerade die unglaubwürdige Quelle.
    return { elapsedMs: Math.max(0, monoDelta), source: 'monotonic', anomaly: 'wall-clock-back' };
  }

  // Normalfall. Auf die Wanduhrspanne begrenzt, damit Invariante I16 hält.
  return {
    elapsedMs: Math.max(0, Math.min(monoDelta, wallDelta)),
    source: 'monotonic',
    anomaly: 'none',
  };
}

export type TimerPhase = 'fresh' | 'running' | 'warning' | 'over';

/** Schwellen aus dem Design-Handoff: Warnung ab 70 % des Budgets. */
const WARNING_RATIO = 0.7;

export function timerPhase(elapsedMs: number, budgetMs: number): TimerPhase {
  if (elapsedMs <= 0) return 'fresh';
  if (elapsedMs > budgetMs) return 'over';
  if (elapsedMs >= budgetMs * WARNING_RATIO) return 'warning';
  return 'running';
}

/** Für den Ring: 0 bei frisch, 1 bei aufgebrauchtem Budget. Nie über 1. */
export function consumedRatio(elapsedMs: number, budgetMs: number): number {
  if (budgetMs <= 0) return 1;
  return Math.max(0, Math.min(1, elapsedMs / budgetMs));
}
