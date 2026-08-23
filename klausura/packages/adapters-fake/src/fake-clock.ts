import type { ClockPort } from '@klausura/ports';

/**
 * Steuerbare Uhr für Tests. Wanduhr und Monotonzeit lassen sich EINZELN
 * bewegen — nur so sind die Fälle prüfbar, die den Timer gefährden:
 *
 *   advance(ms)          normaler Lauf, beide Uhren gleich
 *   sleep(ms)            Gerät schläft: Wanduhr läuft, Monotonzeit steht
 *   setWallClock(delta)  Nutzer verstellt die Systemzeit, vor oder zurück
 *   restartProcess()     Monotonzeit beginnt neu, Wanduhr bleibt
 */
export class FakeClock implements ClockPort {
  #wall: number;
  #mono: number;

  constructor(startWall = 1_700_000_000_000, startMono = 0) {
    this.#wall = startWall;
    this.#mono = startMono;
  }

  wall(): number { return this.#wall; }
  mono(): number { return this.#mono; }

  /** Beide Uhren laufen gleich weiter — der Normalfall. */
  advance(ms: number): void {
    this.#wall += ms;
    this.#mono += ms;
  }

  /** Gerät schläft: die Wanduhr läuft weiter, die Monotonzeit pausiert. */
  sleep(ms: number): void {
    this.#wall += ms;
  }

  /** Systemzeit wird verstellt. Negativ heisst rückwärts. */
  setWallClock(deltaMs: number): void {
    this.#wall += deltaMs;
  }

  /** Prozessneustart: die Monotonzeit verliert ihren Bezug. */
  restartProcess(monoRestartsAt = 0): void {
    this.#mono = monoRestartsAt;
  }
}
