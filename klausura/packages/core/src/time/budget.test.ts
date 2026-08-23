import { describe, expect, it } from 'vitest';
import { distributeTimeBudget, timeBudgetSeconds } from './budget.js';

describe('timeBudgetSeconds · Zeit folgt den Punkten', () => {
  it('teilt 90 Minuten proportional zu 90 Punkten', () => {
    expect(timeBudgetSeconds(85, 900, 90)).toBe(510); // 8,5 P -> 8,5 min
  });

  it('gibt null bei null Punkten', () => {
    expect(timeBudgetSeconds(0, 900, 90)).toBe(0);
  });

  it('gibt null, wenn die Klausur keine Punkte hat', () => {
    expect(timeBudgetSeconds(50, 0, 90)).toBe(0);
  });
});

describe('distributeTimeBudget · Summe passt exakt, Invariante I5', () => {
  it('verteilt ohne Rest', () => {
    const out = distributeTimeBudget([300, 300, 300], 900, 90);
    expect(out).toEqual([1800, 1800, 1800]);
    expect(out.reduce((a, b) => a + b, 0)).toBe(5400);
  });

  it('erschoepft die Klausurdauer auch bei krummen Anteilen exakt', () => {
    const points = [100, 100, 100];
    const out = distributeTimeBudget(points, 300, 100); // 6000 s auf 3 -> 2000 exakt
    expect(out.reduce((a, b) => a + b, 0)).toBe(6000);
  });

  it('ueberschreitet die Dauer nie, auch wenn die Rundung es wollte', () => {
    const points = [1, 1, 1, 1, 1, 1, 1];
    const out = distributeTimeBudget(points, 7, 1); // 60 s auf 7 Aufgaben
    expect(out.reduce((a, b) => a + b, 0)).toBe(60);
    expect(Math.max(...out) - Math.min(...out)).toBeLessThanOrEqual(1);
  });

  it('gibt jeder Aufgabe mit Punkten mindestens eine Sekunde', () => {
    const out = distributeTimeBudget([1, 1000], 1001, 1);
    expect(out[0]).toBeGreaterThanOrEqual(1);
  });

  it('gibt eine leere Liste fuer eine Klausur ohne Aufgaben', () => {
    expect(distributeTimeBudget([], 0, 90)).toEqual([]);
  });
});
