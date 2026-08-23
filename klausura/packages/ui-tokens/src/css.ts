import { DARK, ELEVATION, LIGHT, ON_SIGNAL, TINT_ALPHA, tint, type Palette } from './colors.js';
import { DURATION, EASING, STAGGER, Z } from './motion.js';
import { FONT_STACK, TYPE, type TypeName } from './type.js';
import { HIT_TARGET_MIN, RADIUS, SPACE } from './space.js';

const paletteVars = (p: Palette): string =>
  Object.entries(p).map(([role, value]) => `  --c-${role}: ${value};`).join('\n');

const tintVars = (p: Palette, alpha: number): string =>
  [`  --c-signal-tint: ${tint(p.signal, alpha)};`,
   `  --c-over-tint: ${tint(p.over, alpha)};`,
   `  --c-warn-tint: ${tint(p.warn, alpha)};`,
   `  --c-ok-tint: ${tint(p.ok, alpha)};`].join('\n');

/**
 * Erzeugt das Stylesheet aus den Tokens. Damit gibt es genau eine Quelle:
 * ändert sich eine Rolle, ändert sich das CSS mit — es kann nicht auseinander
 * laufen, weil niemand die Werte abschreibt.
 */
export function buildTokenCss(): string {
  const typeVars = (Object.keys(TYPE) as TypeName[]).flatMap((name) => {
    const t = TYPE[name];
    const out = [
      `  --t-${name}-size: ${t.size}px;`,
      `  --t-${name}-line: ${t.lineHeight};`,
      `  --t-${name}-weight: ${t.weight};`,
      `  --t-${name}-family: var(--font-${t.family});`,
    ];
    if ('letterSpacing' in t && t.letterSpacing) out.push(`  --t-${name}-tracking: ${t.letterSpacing};`);
    return out;
  }).join('\n');

  return `/* ERZEUGT aus @klausura/ui-tokens. Nicht von Hand ändern. */
:root {
  --font-sans: ${FONT_STACK.sans};
  --font-mono: ${FONT_STACK.mono};

${paletteVars(LIGHT)}
${tintVars(LIGHT, TINT_ALPHA.light)}
  --c-on-signal: ${ON_SIGNAL};
  --elev: ${ELEVATION.light};

  --radius: ${RADIUS}px;
  --hit-target-min: ${HIT_TARGET_MIN}px;
${Object.entries(SPACE).map(([k, v]) => `  --space-${k}: ${v}px;`).join('\n')}

${typeVars}

${Object.entries(DURATION).map(([k, v]) => `  --dur-${k}: ${v}ms;`).join('\n')}
${Object.entries(EASING).map(([k, v]) => `  --ease-${k}: ${v};`).join('\n')}
${Object.entries(STAGGER).map(([k, v]) => `  --stagger-${k}: ${typeof v === 'number' && k !== 'max' ? `${v}ms` : v};`).join('\n')}
${Object.entries(Z).map(([k, v]) => `  --z-${k}: ${v};`).join('\n')}

  --t-hover: var(--dur-quick) var(--ease-out);
  --t-press: var(--dur-instant) var(--ease-out);
  --t-enter: var(--dur-base) var(--ease-out);
  --t-switch: var(--dur-base) var(--ease-inOut);
}

[data-mode='dark'] {
${paletteVars(DARK)}
${tintVars(DARK, TINT_ALPHA.dark)}
  --elev: ${ELEVATION.dark};
}

/*
  Reduced Motion ersetzt Bewegung durch einen sofortigen Zustandswechsel —
  nicht durch ersatzloses Streichen. Der Timer bleibt funktional: er misst
  Zeit, er dekoriert nicht. Nur sein Puls entfällt.
*/
@media (prefers-reduced-motion: reduce) {
  :root {
    --dur-instant: 1ms;
    --dur-quick: 1ms;
    --dur-base: 1ms;
    --dur-slow: 1ms;
    --dur-dramatic: 1ms;
    --dur-euphoric: 1ms;
    --stagger-tight: 0ms;
    --stagger-base: 0ms;
    --stagger-cards: 0ms;
    --stagger-cut: 0ms;
    --ease-settle: var(--ease-out);
    --ease-spring: var(--ease-out);
  }
  *:not([data-timer-live]):not([data-timer-live] *) {
    animation-iteration-count: 1 !important;
  }
}
`;
}
