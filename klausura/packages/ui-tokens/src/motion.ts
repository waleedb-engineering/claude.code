/**
 * Motion-System. Einzige Quelle für Dauern, Kurven, Stagger und z-Ebenen.
 * Keine Animation im Produkt trägt hartkodierte ms- oder cubic-bezier-Werte.
 */
export const DURATION = {
  instant: 80,
  quick: 150,
  base: 250,
  slow: 400,
  dramatic: 800,
  /** NUR Timer-Sekundentakt. */
  tick: 1000,
  /** NUR der Bestanden-Moment. Genau eine Stelle im Produkt. */
  euphoric: 900,
} as const;

export const EASING = {
  /** Eintritt. Hauskurve aus dem Design-Handoff. */
  out: 'cubic-bezier(.2, .7, .3, 1)',
  in: 'cubic-bezier(.5, 0, .85, .3)',
  inOut: 'cubic-bezier(.6, 0, .3, 1)',
  /** Landung, gedämpfter Overshoot ≤ 12 %. */
  settle: 'cubic-bezier(.15, 1.12, .4, 1)',
  /** NUR Belohnung. */
  spring: 'cubic-bezier(.2, 1.35, .35, 1)',
  /** NUR Timer. Zeit lügt nicht. */
  linear: 'linear',
} as const;

export const STAGGER = { tight: 40, base: 60, cards: 90, cut: 240, max: 12 } as const;

/** Lückenhaft nummeriert, damit sich dazwischen etwas einschieben lässt. */
export const Z = {
  base: 0, raise: 10, sticky: 100, scanline: 200,
  flyer: 300, overlay: 400, modal: 500, toast: 600, euphoria: 700,
} as const;
