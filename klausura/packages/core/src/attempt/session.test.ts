import { describe, expect, it } from 'vitest';
import { FakeClock } from '@klausura/adapters-fake';
import { beginAttempt, resumeAttempt, submitAttempt } from './session.js';
import { asAttemptId, asTaskId, checkAttemptTimeline } from '@klausura/model';

const taskId = asTaskId('t-A1');
const id = asAttemptId('a1');

describe('beginAttempt', () => {
  it('startet laufend, ohne Abgabe und ohne Punkte', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    expect(s.attempt.submittedAtWall).toBeNull();
    expect(s.attempt.awardedPoints).toBeNull();
    expect(s.attempt.elapsedMs).toBe(0);
    expect(s.anchors.startedAtMono).not.toBeNull();
  });
});

describe('submitAttempt', () => {
  it('haelt Antwort, Abgabezeitpunkt und verstrichene Zeit fest', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(360_000);
    const done = submitAttempt(s, { value: '12', unit: 'kΩ' }, clock);
    expect(done.answerValue).toBe('12');
    expect(done.answerUnit).toBe('kΩ');
    expect(done.elapsedMs).toBe(360_000);
    expect(done.submittedAtWall).toBe(clock.wall());
  });

  it('erlaubt die Abgabe ohne Antwort', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(1_000);
    expect(submitAttempt(s, null, clock).answerValue).toBeNull();
  });

  it('zaehlt Standby-Zeit mit', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(60_000);
    clock.sleep(120_000);
    expect(submitAttempt(s, null, clock).elapsedMs).toBe(180_000);
  });

  it('weist eine zweite Abgabe ab', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(1_000);
    const done = submitAttempt(s, null, clock);
    expect(() => submitAttempt({ attempt: done, anchors: s.anchors }, null, clock)).toThrow(/bereits abgegeben/i);
  });

  it('erzeugt auch bei zurueckgestellter Uhr keinen Versuch, der I16 verletzt', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(30_000);
    clock.setWallClock(-3_600_000); // Uhr zurueckgestellt waehrend der Bearbeitung
    const done = submitAttempt(s, null, clock);

    // Die gearbeiteten 30 s bleiben erhalten, der Abgabezeitpunkt wird daraus
    // rekonstruiert — und der gespeicherte Versuch ist widerspruchsfrei.
    expect(done.elapsedMs).toBe(30_000);
    expect(checkAttemptTimeline(done)).toEqual([]);
  });

  it('bleibt auch nach Standby I16-konform', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(20_000);
    clock.sleep(200_000);
    expect(checkAttemptTimeline(submitAttempt(s, null, clock))).toEqual([]);
  });
});

describe('resumeAttempt · nach App-Neustart', () => {
  it('setzt einen laufenden Versuch auf der Wanduhr fort', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(300_000);
    clock.restartProcess();

    const resumed = resumeAttempt(s.attempt);
    clock.advance(60_000);
    const done = submitAttempt(resumed, null, clock);
    expect(done.elapsedMs).toBe(360_000);
  });

  it('weist das Fortsetzen eines abgegebenen Versuchs ab', () => {
    const clock = new FakeClock();
    const s = beginAttempt({ id, taskId, maxPoints: 85, mode: 'practice' }, clock);
    clock.advance(1_000);
    const done = submitAttempt(s, null, clock);
    expect(() => resumeAttempt(done)).toThrow(/abgegeben/i);
  });
});
