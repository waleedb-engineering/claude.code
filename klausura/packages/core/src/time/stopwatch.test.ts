import { describe, expect, it } from 'vitest';
import { FakeClock } from '@klausura/adapters-fake';
import { readElapsed, startStopwatch, reanchorAfterRestart, timerPhase } from './stopwatch.js';

describe('Stopwatch · Normallauf', () => {
  it('misst verstrichene Zeit aus der Monotonzeit', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(60_000);
    const r = readElapsed(a, clock);
    expect(r.elapsedMs).toBe(60_000);
    expect(r.source).toBe('monotonic');
    expect(r.anomaly).toBe('none');
  });

  it('startet bei null', () => {
    const clock = new FakeClock();
    expect(readElapsed(startStopwatch(clock), clock).elapsedMs).toBe(0);
  });

  it('driftet ueber 10 000 Ticks nicht', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    for (let i = 0; i < 10_000; i++) {
      clock.advance(1);
      readElapsed(a, clock);
    }
    // Exakt, nicht ungefaehr: verstrichene Zeit wird gerechnet, nie akkumuliert.
    expect(readElapsed(a, clock).elapsedMs).toBe(10_000);
  });
});

describe('Stopwatch · Standby', () => {
  it('zaehlt die Schlafzeit mit, wenn die Monotonzeit pausiert hat', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(10_000);
    clock.sleep(60_000);   // Wanduhr laeuft, Monotonzeit steht
    clock.advance(5_000);
    const r = readElapsed(a, clock);
    expect(r.elapsedMs).toBe(75_000);
    expect(r.source).toBe('wall');
    expect(r.anomaly).toBe('device-slept');
  });

  it('bleibt korrekt, wenn die Monotonzeit im Standby weiterlief', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(75_000); // Plattform, auf der mono im Schlaf weiterlaeuft
    const r = readElapsed(a, clock);
    expect(r.elapsedMs).toBe(75_000);
    expect(r.source).toBe('monotonic');
  });
});

describe('Stopwatch · verstellte Systemzeit', () => {
  it('ignoriert eine rueckwaerts gestellte Uhr und meldet die Anomalie', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(300_000);          // 5 min gearbeitet
    clock.setWallClock(-3_600_000);  // Uhr eine Stunde zurueck
    const r = readElapsed(a, clock);
    expect(r.elapsedMs).toBe(300_000);
    expect(r.source).toBe('monotonic');
    expect(r.anomaly).toBe('wall-clock-back');
  });

  it('gibt bei rueckwaerts gestellter Uhr nie negative Zeit zurueck', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.setWallClock(-10_000_000);
    expect(readElapsed(a, clock).elapsedMs).toBeGreaterThanOrEqual(0);
  });

  it('behandelt einen Vorwaertssprung wie Standby — beides ist von aussen nicht unterscheidbar', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(60_000);
    clock.setWallClock(7_200_000); // zwei Stunden vor
    const r = readElapsed(a, clock);
    expect(r.source).toBe('wall');
    expect(r.anomaly).toBe('device-slept');
  });
});

describe('Stopwatch · Prozessneustart', () => {
  it('setzt nach Neustart auf der Wanduhr fort', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(420_000);      // 7 min gearbeitet
    clock.restartProcess();      // App neu gestartet, Monotonzeit ohne Bezug
    const resumed = reanchorAfterRestart(a.startedAtWall);
    const r = readElapsed(resumed, clock);
    expect(r.elapsedMs).toBe(420_000);
    expect(r.source).toBe('wall');
  });

  it('laeuft nach dem Neustart weiter', () => {
    const clock = new FakeClock();
    const a = startStopwatch(clock);
    clock.advance(420_000);
    clock.restartProcess();
    const resumed = reanchorAfterRestart(a.startedAtWall);
    clock.advance(60_000);
    expect(readElapsed(resumed, clock).elapsedMs).toBe(480_000);
  });
});

describe('timerPhase · Schwellen aus dem Design-Handoff', () => {
  const budget = 600_000; // 10 min
  it('frisch bei null', () => expect(timerPhase(0, budget)).toBe('fresh'));
  it('laufend unter 70 Prozent', () => expect(timerPhase(419_000, budget)).toBe('running'));
  it('warnt ab genau 70 Prozent', () => expect(timerPhase(420_000, budget)).toBe('warning'));
  it('warnt bis zum Budget', () => expect(timerPhase(600_000, budget)).toBe('warning'));
  it('ueberzogen darueber', () => expect(timerPhase(600_001, budget)).toBe('over'));
});
