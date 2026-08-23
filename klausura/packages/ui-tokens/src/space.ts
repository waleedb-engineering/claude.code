/** 4-pt-Skala aus README 5.3. Keine Zwischenwerte. */
export const SPACE = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;
export type SpaceName = keyof typeof SPACE;

/** Radius kommt aus dem Theme. Laborgerät: 2 px. Nie hartkodieren. */
export const RADIUS = 2;

/** Mindestgrösse für Tippziele auf Mobile. Nie unterschreiten. */
export const HIT_TARGET_MIN = 44;

/** Umfang des Timer-Rings bei r ≈ 21 (README, Komponente 1). */
export const TIMER_RING_RADIUS = 21;
export const TIMER_RING_CIRCUMFERENCE = 131.9;
