/**
 * Punkte werden als ganzzahlige ZEHNTELPUNKTE gehalten, nie als Kommazahl.
 *
 * Grund: Invariante I1 und I2 sind Summengleichheiten. Mit Gleitkomma wäre
 * jede Summenprüfung eine Toleranzfrage; als Ganzzahl ist sie exakt. Die
 * Klausurpraxis kennt halbe und viertel Punkte, also genügt ein Zehntel.
 *
 * `85` ist "8,5 P". Formatiert wird erst in der Anzeige.
 */
export type PointsTenths = number;

export const pointsFromDecimal = (value: number): PointsTenths => Math.round(value * 10);
export const pointsToDecimal = (tenths: PointsTenths): number => tenths / 10;

/** Deutsche Schreibweise mit Komma, wie im Design-Handoff gefordert. */
export const formatPoints = (tenths: PointsTenths): string => {
  const whole = Math.trunc(Math.abs(tenths) / 10);
  const frac = Math.abs(tenths) % 10;
  const sign = tenths < 0 ? '-' : '';
  return frac === 0 ? `${sign}${whole}` : `${sign}${whole},${frac}`;
};
