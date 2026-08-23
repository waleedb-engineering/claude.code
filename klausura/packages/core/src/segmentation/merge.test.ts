import { describe, expect, it } from 'vitest';
import { mergeSegmentation, pointSumStatus } from './merge.js';
import type { SegmentCandidate } from './merge.js';
import { asPageArtifactId, asSegmentOverrideId } from '@klausura/model';
import type { NormRect, SegmentOverride } from '@klausura/model';

const rect = (x: number): NormRect => ({ x, y: 0.1, width: 0.5, height: 0.2 });
const page = asPageArtifactId('p1');

const candidate = (ordinal: string, points: number, x = 0.1): SegmentCandidate => ({
  pageArtifactId: page, ordinal, points, topic: null, rect: rect(x), confidence: 0.9,
});

const override = (
  ordinal: string, points: number,
  action: SegmentOverride['action'] = 'create', x = 0.2, createdAt = 1,
): SegmentOverride => ({
  id: asSegmentOverrideId(`o-${ordinal}-${createdAt}`),
  pageArtifactId: page, action, ordinal, points, topic: 'Netzwerke', rect: rect(x), createdAt,
});

describe('mergeSegmentation · Invariante I12', () => {
  it('liefert die Kandidaten, wenn es keine Korrektur gibt', () => {
    const out = mergeSegmentation([candidate('A1', 400)], []);
    expect(out).toHaveLength(1);
    expect(out[0]?.ordinal).toBe('A1');
    expect(out[0]?.origin).toBe('automatic');
  });

  it('laesst die Korrektur gewinnen — die Automatik ueberschreibt sie nie', () => {
    const out = mergeSegmentation([candidate('A1', 400)], [override('A1', 850, 'adjust')]);
    expect(out).toHaveLength(1);
    expect(out[0]?.points).toBe(850);
    expect(out[0]?.origin).toBe('manual');
  });

  it('behaelt die Korrektur auch nach einem erneuten Automatiklauf', () => {
    const overrides = [override('A1', 850, 'adjust')];
    const firstRun = mergeSegmentation([candidate('A1', 400)], overrides);
    // Zweiter Lauf, die Automatik schlaegt jetzt etwas anderes vor:
    const secondRun = mergeSegmentation([candidate('A1', 999, 0.7)], overrides);
    expect(secondRun[0]?.points).toBe(firstRun[0]?.points);
    expect(secondRun[0]?.points).toBe(850);
  });

  it('entfernt eine verworfene Aufgabe', () => {
    const out = mergeSegmentation([candidate('A1', 400)], [override('A1', 0, 'reject')]);
    expect(out).toEqual([]);
  });

  it('nimmt eine rein manuell angelegte Aufgabe auf', () => {
    const out = mergeSegmentation([], [override('A9', 120, 'create')]);
    expect(out).toHaveLength(1);
    expect(out[0]?.origin).toBe('manual');
  });

  it('nimmt bei mehreren Korrekturen zur selben Aufgabe die juengste', () => {
    const out = mergeSegmentation([], [override('A1', 100, 'create', 0.2, 1), override('A1', 300, 'adjust', 0.2, 5)]);
    expect(out).toHaveLength(1);
    expect(out[0]?.points).toBe(300);
  });

  it('traegt das Thema aus der Korrektur weiter', () => {
    const out = mergeSegmentation([], [override('A1', 120)]);
    expect(out[0]?.topic).toBe('Netzwerke');
  });

  it('sortiert nach Aufgabennummer', () => {
    const out = mergeSegmentation([candidate('A10', 100), candidate('A2', 100)], []);
    expect(out.map((t) => t.ordinal)).toEqual(['A2', 'A10']);
  });
});

describe('pointSumStatus · die Kreuzprobe der Segmentierung', () => {
  it('meldet Gleichstand', () => {
    const s = pointSumStatus([400, 500], 900);
    expect(s.kind).toBe('match');
    expect(s.differenceTenths).toBe(0);
  });

  it('meldet fehlende Punkte — Verdacht: zwei Aufgaben als eine erfasst', () => {
    const s = pointSumStatus([400], 900);
    expect(s.kind).toBe('short');
    expect(s.differenceTenths).toBe(-500);
    expect(s.message).toContain('50');
  });

  it('meldet ueberzaehlige Punkte — Verdacht: eine Aufgabe als zwei erfasst', () => {
    expect(pointSumStatus([400, 500, 100], 900).kind).toBe('over');
  });

  it('meldet den Leerzustand vor der ersten Markierung', () => {
    expect(pointSumStatus([], 900).kind).toBe('empty');
  });
});
