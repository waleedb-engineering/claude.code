/**
 * Farbrollen aus design_handoff_klausura/README.md Abschnitt 5.1,
 * Theme "Laborgerät / Oszilloskop". Werte sind dort final — hier steht die
 * einzige Kopie im Code. Keine Komponente schreibt je einen Hex-Wert.
 */
export const COLOR_ROLES = [
  'paper', 'panel', 'chrome', 'head', 'grid', 'rule',
  'ink', 'ink60', 'ink30', 'track',
  'signal', 'warn', 'over', 'ok',
] as const;

export type ColorRole = (typeof COLOR_ROLES)[number];
export type Mode = 'light' | 'dark';

export type Palette = Readonly<Record<ColorRole, string>>;

export const LIGHT: Palette = {
  paper: '#EFEFEC',
  panel: '#F7F7F4',
  chrome: '#FFFFFF',
  head: '#FFFFFF',
  grid: '#FBFBF9',
  rule: '#E6E6E1',
  ink: '#14150F',
  ink60: '#6B6B66',
  ink30: '#B4B4AE',
  track: '#E6E6E1',
  signal: '#FF5A00',
  warn: '#B45309',
  over: '#C2280F',
  ok: '#2F6B3A',
};

/** Fokus-Dunkel. Im Simulator erzwungen, unabhängig vom gewählten Theme. */
export const DARK: Palette = {
  paper: '#0B0C09',
  panel: '#111310',
  chrome: '#141612',
  head: '#141612',
  grid: '#101209',
  rule: '#26281F',
  ink: '#F2F2EC',
  ink60: '#8E9086',
  ink30: '#4A4C44',
  track: '#26281F',
  signal: '#FF7A2E',
  warn: '#E0A64A',
  over: '#FF5240',
  ok: '#5FBF7A',
};

/** Genau eine Elevationsstufe je Modus. Karten trennen Hairlines, keine Schatten. */
export const ELEVATION: Readonly<Record<Mode, string>> = {
  light: '0 1px 2px rgba(20,21,15,.08)',
  dark: '0 2px 10px rgba(0,0,0,.5)',
};

/** Text auf signal-Flächen. Im Laborgerät-Theme weiss. */
export const ON_SIGNAL = '#FFFFFF';

export const PALETTES: Readonly<Record<Mode, Palette>> = { light: LIGHT, dark: DARK };

/**
 * Getönte Flächen: Auswahl- und Aktivzustände sind `signal` mit Alpha.
 * Hell 5 %, dunkel 12 % — aus Abschnitt 5.1 des Handoffs.
 */
export const TINT_ALPHA: Readonly<Record<Mode, number>> = { light: 0.05, dark: 0.12 };

export function tint(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
