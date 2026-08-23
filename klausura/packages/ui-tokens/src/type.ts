/**
 * Typo-Skala aus README 5.2. Mono trägt ALLE Zahlen, Labels und Formeln.
 * Regel: `font-variant-numeric: tabular-nums` auf jedem Element, dessen Zahl
 * sich ändern kann — sonst springt die Anzeige beim Zählen.
 */
export type FontFamily = 'sans' | 'mono';

export interface TypeToken {
  readonly size: number;
  readonly lineHeight: number;
  readonly weight: number;
  readonly family: FontFamily;
  readonly letterSpacing?: string;
  readonly uppercase?: boolean;
  readonly tabular?: boolean;
}

export const TYPE = {
  'display-34': { size: 34, lineHeight: 1.18, weight: 600, family: 'sans', letterSpacing: '-.025em' },
  'display-32': { size: 32, lineHeight: 1.1, weight: 600, family: 'sans', letterSpacing: '-.02em' },
  'num-26': { size: 26, lineHeight: 1.05, weight: 600, family: 'mono', letterSpacing: '-.02em', tabular: true },
  'title-24': { size: 24, lineHeight: 1.2, weight: 600, family: 'sans', letterSpacing: '-.02em' },
  'num-22': { size: 22, lineHeight: 1.2, weight: 400, family: 'mono', tabular: true },
  'title-19': { size: 19, lineHeight: 1.3, weight: 600, family: 'sans', letterSpacing: '-.01em' },
  'title-18': { size: 18, lineHeight: 1.3, weight: 600, family: 'sans', letterSpacing: '-.01em' },
  'body-16': { size: 16, lineHeight: 1.4, weight: 500, family: 'sans' },
  'body-15': { size: 15, lineHeight: 1.6, weight: 400, family: 'sans' },
  'body-14': { size: 14, lineHeight: 1.65, weight: 400, family: 'sans' },
  'body-13': { size: 13, lineHeight: 1.5, weight: 400, family: 'sans' },
  'body-12': { size: 12, lineHeight: 1.4, weight: 400, family: 'sans' },
  'num-13': { size: 13, lineHeight: 1.4, weight: 400, family: 'mono', tabular: true },
  'label-11': { size: 11, lineHeight: 1.2, weight: 400, family: 'mono', letterSpacing: '.14em', uppercase: true },
  'label-10': { size: 10, lineHeight: 1.2, weight: 400, family: 'mono', letterSpacing: '.14em', uppercase: true },
  'label-9': { size: 9, lineHeight: 1.2, weight: 400, family: 'mono', letterSpacing: '.12em', uppercase: true },
} as const satisfies Record<string, TypeToken>;

export type TypeName = keyof typeof TYPE;

export const FONT_STACK: Readonly<Record<FontFamily, string>> = {
  sans: "'IBM Plex Sans', system-ui, -apple-system, sans-serif",
  mono: "'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace",
};
