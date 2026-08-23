import { describe, expect, it } from 'vitest';
import {
  checkAttemptPoints, checkAttemptTimeline, checkExamPointSum,
  checkRectWithinPage, checkSubtaskPointSum, checkTimeBudgetSum,
} from './invariants.js';
import { asAttemptId, asExamPaperId, asPageArtifactId, asTaskId } from './ids.js';
import type { Attempt, NormRect, Task, Subtask } from './entities.js';

const rect: NormRect = { x: 0.1, y: 0.1, width: 0.5, height: 0.2 };

const task = (ordinal: string, points: number, budget = 600): Task => ({
  id: asTaskId(`t-${ordinal}`),
  examPaperId: asExamPaperId('e1'),
  ordinal, title: `Aufgabe ${ordinal}`,
  points, timeBudgetSeconds: budget,
  kind: 'calculation', topic: null,
  pageArtifactId: asPageArtifactId('p1'), rect,
});

const subtask = (ordinal: string, points: number): Subtask => ({
  id: `s-${ordinal}` as Subtask['id'], taskId: asTaskId('t-A1'), ordinal, points,
});

const attempt = (over: Partial<Attempt> = {}): Attempt => ({
  id: asAttemptId('a1'), taskId: asTaskId('t-A1'), mode: 'practice',
  startedAtWall: 1_000_000, submittedAtWall: 1_600_000, elapsedMs: 600_000,
  answerValue: '12', answerUnit: 'kΩ', awardedPoints: 60, maxPoints: 85,
  ...over,
});

describe('I1 · Summe der Teilaufgabenpunkte gleich Aufgabenpunkte', () => {
  it('akzeptiert eine Aufgabe ohne Teilaufgaben', () => {
    expect(checkSubtaskPointSum(task('A1', 85), [])).toEqual([]);
  });

  it('akzeptiert 4,0 + 4,5 gegen 8,5 Punkte', () => {
    expect(checkSubtaskPointSum(task('A1', 85), [subtask('a', 40), subtask('b', 45)])).toEqual([]);
  });

  it('meldet eine Abweichung mit Soll und Ist', () => {
    const v = checkSubtaskPointSum(task('A1', 85), [subtask('a', 40), subtask('b', 40)]);
    expect(v).toHaveLength(1);
    expect(v[0]?.code).toBe('I1');
    expect(v[0]?.message).toContain('8,5');
    expect(v[0]?.message).toContain('8');
  });
});

describe('I2 · Summe der Aufgabenpunkte gleich Klausurpunkte', () => {
  it('akzeptiert die exakte Summe', () => {
    expect(checkExamPointSum(900, [task('A1', 400), task('A2', 500)])).toEqual([]);
  });

  it('meldet eine zu kleine Summe — der Fall "zwei Aufgaben als eine"', () => {
    const v = checkExamPointSum(900, [task('A1', 400)]);
    expect(v).toHaveLength(1);
    expect(v[0]?.code).toBe('I2');
  });

  it('meldet eine zu grosse Summe — der Fall "eine Aufgabe als zwei"', () => {
    expect(checkExamPointSum(900, [task('A1', 400), task('A2', 500), task('A3', 100)])).toHaveLength(1);
  });
});

describe('I4 · Erreichte Punkte liegen zwischen null und Maximum', () => {
  it('akzeptiert einen Wert im Band', () => {
    expect(checkAttemptPoints(attempt({ awardedPoints: 60, maxPoints: 85 }))).toEqual([]);
  });

  it('akzeptiert einen noch nicht bewerteten Versuch', () => {
    expect(checkAttemptPoints(attempt({ awardedPoints: null }))).toEqual([]);
  });

  it('meldet negative Punkte', () => {
    expect(checkAttemptPoints(attempt({ awardedPoints: -10 }))[0]?.code).toBe('I4');
  });

  it('meldet mehr als das Maximum', () => {
    expect(checkAttemptPoints(attempt({ awardedPoints: 90, maxPoints: 85 }))[0]?.code).toBe('I4');
  });
});

describe('I5 · Summe der Zeitbudgets passt in die Klausurdauer', () => {
  it('akzeptiert eine ausgeschoepfte Dauer', () => {
    expect(checkTimeBudgetSum(20, [task('A1', 400, 600), task('A2', 500, 600)])).toEqual([]);
  });

  it('meldet Ueberschreitung der Klausurdauer', () => {
    expect(checkTimeBudgetSum(15, [task('A1', 400, 600), task('A2', 500, 600)])[0]?.code).toBe('I5');
  });
});

describe('I11 · Markierung liegt innerhalb der Seite', () => {
  it('akzeptiert ein Rechteck im Blatt', () => {
    expect(checkRectWithinPage({ x: 0, y: 0, width: 1, height: 1 })).toEqual([]);
  });

  it('meldet einen Ueberhang nach rechts', () => {
    expect(checkRectWithinPage({ x: 0.8, y: 0.1, width: 0.3, height: 0.1 })[0]?.code).toBe('I11');
  });

  it('meldet negative Herkunft', () => {
    expect(checkRectWithinPage({ x: -0.1, y: 0.1, width: 0.2, height: 0.1 })[0]?.code).toBe('I11');
  });

  it('meldet eine Flaeche ohne Ausdehnung', () => {
    expect(checkRectWithinPage({ x: 0.1, y: 0.1, width: 0, height: 0.1 })[0]?.code).toBe('I11');
  });
});

describe('I16 · Zeitachse des Versuchs ist widerspruchsfrei', () => {
  it('akzeptiert Abgabe nach Start mit passender Dauer', () => {
    expect(checkAttemptTimeline(attempt())).toEqual([]);
  });

  it('akzeptiert einen laufenden Versuch ohne Abgabe', () => {
    expect(checkAttemptTimeline(attempt({ submittedAtWall: null, elapsedMs: 120_000 }))).toEqual([]);
  });

  it('meldet Abgabe vor Start', () => {
    expect(checkAttemptTimeline(attempt({ submittedAtWall: 900_000 }))[0]?.code).toBe('I16');
  });

  it('meldet negative verstrichene Zeit', () => {
    expect(checkAttemptTimeline(attempt({ elapsedMs: -1 }))[0]?.code).toBe('I16');
  });

  it('meldet eine Dauer, die laenger ist als das Zeitfenster erlaubt', () => {
    // Standby darf elapsed nie GROESSER machen als die Wanduhrspanne.
    expect(checkAttemptTimeline(attempt({ elapsedMs: 700_000 }))[0]?.code).toBe('I16');
  });
});
