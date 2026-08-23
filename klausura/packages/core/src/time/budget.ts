import type { PointsTenths } from '@klausura/model';

/**
 * Zeit folgt den Punkten. Das ist die inhaltliche Aussage des Produkts:
 * eine Aufgabe, die 10 % der Punkte bringt, bekommt 10 % der Klausurzeit.
 */
export function timeBudgetSeconds(
  points: PointsTenths,
  totalPoints: PointsTenths,
  durationMinutes: number,
): number {
  if (totalPoints <= 0 || points <= 0) return 0;
  return Math.round((points / totalPoints) * durationMinutes * 60);
}

/**
 * Verteilt die Klausurdauer auf alle Aufgaben, so dass die Summe EXAKT der
 * verfügbaren Zeit entspricht (Invariante I5).
 *
 * Einzelnes Runden je Aufgabe würde die Summe um ein paar Sekunden über die
 * Klausurdauer heben und I5 verletzen. Deshalb Größte-Reste-Verfahren:
 * erst abrunden, dann die übrigen Sekunden an die größten Reste vergeben.
 */
export function distributeTimeBudget(
  points: readonly PointsTenths[],
  totalPoints: PointsTenths,
  durationMinutes: number,
): number[] {
  if (points.length === 0) return [];

  const available = durationMinutes * 60;
  if (totalPoints <= 0 || available <= 0) return points.map(() => 0);

  const exact = points.map((p) => (p <= 0 ? 0 : (p / totalPoints) * available));
  const floors = exact.map((v) => Math.floor(v));

  // Jede Aufgabe mit Punkten bekommt mindestens eine Sekunde — ein Budget von
  // null Sekunden wäre in der UI ein sofort überzogener Timer.
  const withMinimum = floors.map((v, i) => ((points[i] ?? 0) > 0 ? Math.max(1, v) : v));

  let remaining = available - withMinimum.reduce((a, b) => a + b, 0);

  const byRemainder = exact
    .map((v, i) => ({ i, rest: v - Math.floor(v) }))
    .sort((a, b) => b.rest - a.rest);

  const out = [...withMinimum];
  // Übrige Sekunden vergeben.
  for (let k = 0; remaining > 0 && byRemainder.length > 0; k++) {
    const idx = byRemainder[k % byRemainder.length]?.i;
    if (idx === undefined) break;
    out[idx] = (out[idx] ?? 0) + 1;
    remaining--;
  }
  // Zu viel vergeben (durch die Mindestsekunde): bei den größten wieder abziehen.
  for (let k = 0; remaining < 0; k++) {
    const idx = byRemainder[byRemainder.length - 1 - (k % byRemainder.length)]?.i;
    if (idx === undefined) break;
    if ((out[idx] ?? 0) > 1) {
      out[idx] = (out[idx] ?? 0) - 1;
      remaining++;
    } else if (k > byRemainder.length * 2) {
      break; // nichts mehr abziehbar
    }
  }

  return out;
}
