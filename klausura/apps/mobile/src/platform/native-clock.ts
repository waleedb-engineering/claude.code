import type { ClockPort } from '@klausura/ports';

/**
 * Hermes stellt `performance.now()` bereit; falls nicht, fällt die
 * Monotonzeit auf die Wanduhr zurück. Der Stopwatch-Kern kommt damit klar:
 * beide Uhren laufen dann synchron, und die Standby-Erkennung greift ueber
 * die Wanduhr.
 */
const mono: () => number =
  typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? () => performance.now()
    : () => Date.now();

export const nativeClock: ClockPort = { wall: () => Date.now(), mono };
