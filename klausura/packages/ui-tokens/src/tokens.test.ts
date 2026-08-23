import { describe, expect, it } from 'vitest';
import { COLOR_ROLES, DARK, LIGHT, PALETTES } from './colors.js';
import { TYPE } from './type.js';
import { buildTokenCss } from './css.js';
import { DURATION } from './motion.js';

describe('Farbrollen', () => {
  it('definiert jede Rolle in hell und in dunkel', () => {
    for (const role of COLOR_ROLES) {
      expect(LIGHT[role], `hell: ${role}`).toMatch(/^#[0-9A-F]{6}$/i);
      expect(DARK[role], `dunkel: ${role}`).toMatch(/^#[0-9A-F]{6}$/i);
    }
  });

  it('laesst keine Rolle in beiden Modi identisch, ausser wo das gewollt ist', () => {
    // head und chrome sind im Laborgeraet-Theme je Modus gleich — das ist so
    // spezifiziert. Alles andere muss sich unterscheiden, sonst ist eine
    // Rolle beim Uebertragen verrutscht.
    const intentionallyEqual = new Set(['head', 'chrome']);
    const same = COLOR_ROLES.filter((r) => LIGHT[r] === DARK[r] && !intentionallyEqual.has(r));
    expect(same).toEqual([]);
  });

  it('kennt genau zwei Modi', () => {
    expect(Object.keys(PALETTES).sort()).toEqual(['dark', 'light']);
  });
});

describe('Typo-Skala', () => {
  it('gibt jedem Token Groesse, Zeile, Gewicht und Familie', () => {
    for (const [name, t] of Object.entries(TYPE)) {
      expect(t.size, name).toBeGreaterThan(0);
      expect(t.lineHeight, name).toBeGreaterThan(0);
      expect(t.weight, name).toBeGreaterThanOrEqual(400);
      expect(['sans', 'mono']).toContain(t.family);
    }
  });

  it('setzt jede Zahl in Mono mit tabular-nums', () => {
    for (const [name, t] of Object.entries(TYPE)) {
      if (!name.startsWith('num-')) continue;
      expect(t.family, name).toBe('mono');
      expect('tabular' in t && t.tabular, name).toBe(true);
    }
  });
});

describe('Motion', () => {
  it('haelt sich an die 800-ms-Grenze, ausser beim Bestanden-Moment', () => {
    const overLimit = Object.entries(DURATION)
      .filter(([name, ms]) => ms > 800 && name !== 'euphoric' && name !== 'tick')
      .map(([name]) => name);
    expect(overLimit).toEqual([]);
  });
});

describe('buildTokenCss', () => {
  const css = buildTokenCss();

  it('gibt jede Farbrolle als Variable aus', () => {
    for (const role of COLOR_ROLES) expect(css).toContain(`--c-${role}:`);
  });

  it('enthaelt einen Dunkelblock', () => {
    expect(css).toContain("[data-mode='dark']");
  });

  it('enthaelt einen Reduced-Motion-Block', () => {
    expect(css).toContain('prefers-reduced-motion: reduce');
  });

  it('nimmt den Timer von der Bewegungsabschaltung aus', () => {
    expect(css).toContain('data-timer-live');
  });
});
