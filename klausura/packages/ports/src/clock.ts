/**
 * Zwei Uhren, absichtlich getrennt.
 *
 * `wall` ist die Systemzeit: überlebt Prozessneustart und Standby, kann aber
 * vom Nutzer oder von NTP verstellt werden — auch rückwärts.
 * `mono` ist eine monoton wachsende Quelle: nie rückwärts, aber ohne Bezug zu
 * einem Datum und über einen Prozessneustart hinweg wertlos.
 *
 * Der Timer braucht beide. Siehe core/time/stopwatch.
 */
export interface ClockPort {
  /** Millisekunden seit Epoche. */
  wall(): number;
  /** Monoton wachsende Millisekunden ohne Datumsbezug. */
  mono(): number;
}
