import { formatPoints } from '@klausura/model';
import type { NormRect, PageArtifactId, PointsTenths, SegmentOverride } from '@klausura/model';

/**
 * Vorschlag der Automatik. In M1 gibt es keine Automatik — die Liste ist dann
 * leer und alles kommt aus Korrekturen. Ab M3 füllt die Segmentierung sie.
 */
export interface SegmentCandidate {
  readonly pageArtifactId: PageArtifactId;
  readonly ordinal: string;
  readonly points: PointsTenths;
  readonly topic: string | null;
  readonly rect: NormRect;
  /** 0…1. Unter 0.7 markiert die Review-UI den Kandidaten. */
  readonly confidence: number;
}

export interface MergedSegment {
  readonly pageArtifactId: PageArtifactId;
  readonly ordinal: string;
  readonly points: PointsTenths;
  readonly topic: string | null;
  readonly rect: NormRect;
  readonly origin: 'automatic' | 'manual';
  readonly confidence: number;
}

/** Aufgabennummern natürlich sortieren: A2 vor A10, nicht danach. */
function compareOrdinals(a: string, b: string): number {
  return a.localeCompare(b, 'de', { numeric: true, sensitivity: 'base' });
}

/**
 * Legt Nutzerkorrekturen über das Automatikergebnis.
 *
 * Das ist die wichtigste Zusage der Ingest-Pipeline (Invariante I12): ein
 * erneuter Automatiklauf darf eine Korrektur weder überschreiben noch
 * löschen. Deshalb ist die Korrektur die Basis und der Kandidat der Zusatz —
 * nicht umgekehrt.
 */
export function mergeSegmentation(
  candidates: readonly SegmentCandidate[],
  overrides: readonly SegmentOverride[],
): MergedSegment[] {
  // Je Aufgabennummer gewinnt die jüngste Korrektur.
  const newestByOrdinal = new Map<string, SegmentOverride>();
  for (const o of overrides) {
    const existing = newestByOrdinal.get(o.ordinal);
    if (existing === undefined || o.createdAt >= existing.createdAt) {
      newestByOrdinal.set(o.ordinal, o);
    }
  }

  const out: MergedSegment[] = [];

  for (const c of candidates) {
    const o = newestByOrdinal.get(c.ordinal);
    if (o === undefined) {
      out.push({ ...c, origin: 'automatic' });
      continue;
    }
    if (o.action === 'reject') continue;
    out.push({
      pageArtifactId: o.pageArtifactId,
      ordinal: o.ordinal,
      points: o.points,
      topic: o.topic,
      rect: o.rect,
      origin: 'manual',
      confidence: 1,
    });
  }

  // Korrekturen ohne zugehörigen Kandidaten: manuell angelegte Aufgaben.
  const covered = new Set(candidates.map((c) => c.ordinal));
  for (const o of newestByOrdinal.values()) {
    if (covered.has(o.ordinal) || o.action === 'reject') continue;
    out.push({
      pageArtifactId: o.pageArtifactId,
      ordinal: o.ordinal,
      points: o.points,
      topic: o.topic,
      rect: o.rect,
      origin: 'manual',
      confidence: 1,
    });
  }

  return out.sort((a, b) => compareOrdinals(a.ordinal, b.ordinal));
}

export type PointSumKind = 'empty' | 'match' | 'short' | 'over';

export interface PointSumStatus {
  readonly kind: PointSumKind;
  readonly sumTenths: PointsTenths;
  readonly expectedTenths: PointsTenths;
  /** Ist minus Soll. Negativ heisst: es fehlen Punkte. */
  readonly differenceTenths: number;
  readonly message: string;
}

/**
 * Die Kreuzprobe der Segmentierung.
 *
 * Sie findet Zerlegungsfehler zuverlässiger als jede Konfidenzzahl: fehlen
 * Punkte, wurden zwei Aufgaben als eine erfasst; sind es zu viele, wurde eine
 * Aufgabe zweimal gezählt. Deshalb ist Invariante I2 hier kein
 * Datenhygiene-Detail, sondern ein Diagnosewerkzeug.
 */
export function pointSumStatus(
  taskPoints: readonly PointsTenths[],
  expectedTenths: PointsTenths,
): PointSumStatus {
  const sumTenths = taskPoints.reduce((a, b) => a + b, 0);
  const differenceTenths = sumTenths - expectedTenths;

  if (taskPoints.length === 0) {
    return {
      kind: 'empty', sumTenths, expectedTenths, differenceTenths,
      message: `Noch keine Aufgabe markiert. Erwartet werden ${formatPoints(expectedTenths)} P.`,
    };
  }
  if (differenceTenths === 0) {
    return {
      kind: 'match', sumTenths, expectedTenths, differenceTenths,
      message: `${formatPoints(sumTenths)} P — stimmt mit der Klausur überein.`,
    };
  }
  if (differenceTenths < 0) {
    return {
      kind: 'short', sumTenths, expectedTenths, differenceTenths,
      message: `${formatPoints(sumTenths)} von ${formatPoints(expectedTenths)} P — ${formatPoints(-differenceTenths)} P fehlen.`,
    };
  }
  return {
    kind: 'over', sumTenths, expectedTenths, differenceTenths,
    message: `${formatPoints(sumTenths)} von ${formatPoints(expectedTenths)} P — ${formatPoints(differenceTenths)} P zu viel.`,
  };
}
