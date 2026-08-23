import { describe, expect, it } from 'vitest';
import { formatDecimal, parseDecimal, parseQuantity } from './quantity.js';

describe('parseDecimal · deutsche Schreibweise', () => {
  it('liest Komma als Dezimaltrennzeichen', () => {
    expect(parseDecimal('12,5')).toBe(12.5);
  });

  it('liest auch den Punkt, weil Tastaturen ihn liefern', () => {
    expect(parseDecimal('12.5')).toBe(12.5);
  });

  it('liest wissenschaftliche Schreibweise', () => {
    expect(parseDecimal('1,5e-3')).toBeCloseTo(0.0015);
  });

  it('liest negative Werte', () => {
    expect(parseDecimal('-4,25')).toBe(-4.25);
  });

  it('verwirft Leereingabe', () => {
    expect(parseDecimal('')).toBeNull();
  });

  it('verwirft Text', () => {
    expect(parseDecimal('zwoelf')).toBeNull();
  });

  it('verwirft zwei Trennzeichen', () => {
    expect(parseDecimal('1,2,3')).toBeNull();
  });
});

describe('parseQuantity · Praefix bleibt stehen', () => {
  it('haelt Zahl und Einheit getrennt', () => {
    expect(parseQuantity('12', 'kΩ')).toEqual({ value: 12, unit: 'kΩ' });
  });

  it('rechnet kOhm NICHT stillschweigend in Ohm um', () => {
    // CLAUDE.md Regel 8: die Eingabe rechnet nie um. Nur die Bewertung darf,
    // und vergibt dabei E-POT. Das ist M2 — hier zaehlt nur: nichts passiert.
    const q = parseQuantity('12', 'kΩ');
    expect(q?.value).toBe(12);
    expect(q?.unit).toBe('kΩ');
  });

  it('nimmt eine Eingabe ohne Einheit an', () => {
    expect(parseQuantity('12', '')).toEqual({ value: 12, unit: '' });
  });

  it('verwirft eine ungueltige Zahl', () => {
    expect(parseQuantity('abc', 'Ω')).toBeNull();
  });
});

describe('formatDecimal · zurueck in deutsche Schreibweise', () => {
  it('setzt ein Komma', () => expect(formatDecimal(12.5)).toBe('12,5'));
  it('laesst ganze Zahlen ganz', () => expect(formatDecimal(12)).toBe('12'));
});
