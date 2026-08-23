import { formatPoints, type Task } from '@klausura/model';
import { PointsBadge } from './PointsBadge.js';

/** Komponente 3 aus dem Handoff. Obere 3-px-Kante trägt die Beherrschungsfarbe. */
export function TaskCard({
  task, masteryPercent = null, onOpen,
}: { task: Task; masteryPercent?: number | null; onOpen: (task: Task) => void }) {
  const edge =
    masteryPercent === null ? 'var(--c-rule)'
    : masteryPercent < 30 ? 'var(--c-over)'
    : masteryPercent < 60 ? 'var(--c-warn)'
    : 'var(--c-ok)';

  const minutes = Math.round(task.timeBudgetSeconds / 60);

  return (
    <button
      type="button"
      className="task-card"
      data-testid="task-card"
      data-ordinal={task.ordinal}
      onClick={() => onOpen(task)}
    >
      <span className="task-card__edge" style={{ background: edge }} aria-hidden="true" />
      <span className="task-card__head">
        <span className="task-card__ordinal">{task.ordinal}</span>
        <PointsBadge points={task.points} />
      </span>
      <span className="task-card__title">{task.title}</span>
      <span className="task-card__meta">
        <span className="label">{task.topic ?? 'OHNE THEMA'}</span>
        <span className="mono">{minutes} MIN</span>
      </span>
      <span className="task-card__mastery">
        <span className="task-card__track">
          <span
            className="task-card__fill"
            style={{ width: `${masteryPercent ?? 0}%`, background: edge }}
          />
        </span>
        <span className="mono task-card__percent">
          {masteryPercent === null ? '—' : `${masteryPercent} %`}
        </span>
      </span>
      <span className="sr-only">{formatPoints(task.points)} Punkte</span>
    </button>
  );
}
