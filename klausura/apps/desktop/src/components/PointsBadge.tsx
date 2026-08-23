import { formatPoints, type PointsTenths } from '@klausura/model';

export type PointsVariant = 'neutral' | 'earned' | 'lost';

/** Komponente 2 aus dem Handoff: Mono num-13, 1-px-Rahmen, 3px 8px Polster. */
export function PointsBadge({
  points, variant = 'neutral', label = 'P',
}: { points: PointsTenths; variant?: PointsVariant; label?: string }) {
  const color =
    variant === 'earned' ? 'var(--c-ok)' : variant === 'lost' ? 'var(--c-over)' : 'var(--c-ink60)';
  return (
    <span className="points-badge" data-variant={variant} style={{ borderColor: color, color }}>
      {formatPoints(points)} {label}
    </span>
  );
}
