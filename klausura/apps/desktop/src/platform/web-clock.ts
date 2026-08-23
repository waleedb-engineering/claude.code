import type { ClockPort } from '@klausura/ports';

/**
 * `performance.now()` ist monoton und feiner aufgelöst als die Systemzeit;
 * `Date.now()` ist die Wanduhr. Beide werden getrennt gebraucht — warum,
 * steht in core/time/stopwatch.
 */
export const webClock: ClockPort = {
  wall: () => Date.now(),
  mono: () => performance.now(),
};
