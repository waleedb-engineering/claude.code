import { consumedRatio, timerPhase, type TimerPhase } from '@klausura/core';
import { TIMER_RING_CIRCUMFERENCE, TIMER_RING_RADIUS } from '@klausura/ui-tokens';

const PHASE_COLOR: Record<TimerPhase, string> = {
  fresh: 'var(--c-track)',
  running: 'var(--c-signal)',
  warning: 'var(--c-warn)',
  over: 'var(--c-over)',
};

const PHASE_LABEL: Record<TimerPhase, string> = {
  fresh: 'BEREIT',
  running: 'LÄUFT',
  warning: 'ZEIT 70 %',
  over: 'ÜBERZOGEN',
};

/** Sekunden als mm:ss, bei Überschreitung mit führendem Plus. */
export function formatClock(ms: number): string {
  const sign = ms < 0 ? '-' : '';
  const total = Math.floor(Math.abs(ms) / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${sign}${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Komponente 1 aus dem Handoff. SVG-Ring, Umfang 131.9 bei r ≈ 21,
 * stroke-dashoffset trägt den Restanteil.
 *
 * `data-timer-live` nimmt den Ring von der Reduced-Motion-Abschaltung aus:
 * er misst Zeit, er dekoriert nicht.
 */
export function TimerRing({
  elapsedMs, budgetMs, size = 52,
}: { elapsedMs: number; budgetMs: number; size?: number }) {
  const phase = timerPhase(elapsedMs, budgetMs);
  const ratio = consumedRatio(elapsedMs, budgetMs);
  const offset = TIMER_RING_CIRCUMFERENCE * (1 - ratio);
  const remaining = budgetMs - elapsedMs;
  const color = PHASE_COLOR[phase];

  return (
    <div className="timer" data-phase={phase} data-testid="timer">
      <svg
        width={size} height={size} viewBox="0 0 48 48" data-timer-live
        role="img"
        aria-label={`Zeit ${formatClock(Math.abs(remaining))}, ${PHASE_LABEL[phase]}`}
      >
        <circle cx="24" cy="24" r={TIMER_RING_RADIUS} fill="none" stroke="var(--c-track)" strokeWidth="3" />
        <circle
          cx="24" cy="24" r={TIMER_RING_RADIUS} fill="none"
          stroke={color} strokeWidth="3" strokeLinecap="butt"
          strokeDasharray={TIMER_RING_CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 24 24)"
        />
      </svg>
      <div className="timer__readout">
        <div className="timer__value" data-testid="timer-value" style={{ color }}>
          {remaining < 0 ? '+' : ''}{formatClock(remaining)}
        </div>
        <div className="timer__label" data-testid="timer-phase">{PHASE_LABEL[phase]}</div>
      </div>
    </div>
  );
}
