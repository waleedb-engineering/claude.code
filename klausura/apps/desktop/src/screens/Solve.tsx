import { useCallback, useEffect, useRef, useState } from 'react';
import { asAttemptId, formatPoints } from '@klausura/model';
import type { Attempt, Task } from '@klausura/model';
import {
  beginAttempt, readElapsed, resumeAttempt, submitAttempt, timerPhase,
  type AttemptSession,
} from '@klausura/core';
import { findRunningAttempt, listAttempts, saveAttempt } from '@klausura/storage-sqlite';
import { db } from '../platform/db.js';
import { webClock } from '../platform/web-clock.js';
import { TimerRing } from '../components/TimerRing.js';
import { UnitInput } from '../components/UnitInput.js';
import { PointsBadge } from '../components/PointsBadge.js';

/**
 * Screen 04 in Grundform (M1, aus M2 vorgezogen): Aufgabe anzeigen, Zeitbudget
 * aus Punkten, Timer laufen lassen, Antwort als Wert und Einheit erfassen,
 * Versuch speichern. Die fünf Zustände und die Bewertung sind M2.
 */
export function SolveScreen({ task, onBack }: { task: Task; onBack: () => void }) {
  const [session, setSession] = useState<AttemptSession | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState('');
  const [past, setPast] = useState<Attempt[]>([]);
  const frame = useRef<number | null>(null);

  const budgetMs = task.timeBudgetSeconds * 1000;

  const loadPast = useCallback(async () => {
    const storage = await db();
    setPast((await listAttempts(storage, task.id)).filter((a) => a.submittedAtWall !== null));
  }, [task.id]);

  // Laufenden Versuch fortsetzen oder einen neuen beginnen. Genau hier
  // entscheidet sich, ob ein App-Neustart Arbeit kostet.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const storage = await db();
      const running = await findRunningAttempt(storage, task.id);
      if (cancelled) return;

      if (running !== undefined) {
        setSession(resumeAttempt(running));
        setValue(running.answerValue ?? '');
        setUnit(running.answerUnit ?? '');
      } else {
        const fresh = beginAttempt(
          { id: asAttemptId(`att-${task.id}-${webClock.wall()}`), taskId: task.id, maxPoints: task.points, mode: 'practice' },
          webClock,
        );
        await saveAttempt(storage, fresh.attempt);
        await storage.persist();
        if (!cancelled) setSession(fresh);
      }
      await loadPast();
    })();
    return () => { cancelled = true; };
  }, [task.id, task.points, loadPast]);

  // Der Tick treibt nur die Anzeige. Der Wert kommt jedes Mal frisch aus den
  // Zeitstempeln — deshalb kann er nicht driften.
  useEffect(() => {
    if (session === null) return;
    const tick = (): void => {
      setElapsed(readElapsed(session.anchors, webClock).elapsedMs);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => { if (frame.current !== null) cancelAnimationFrame(frame.current); };
  }, [session]);

  async function submit(): Promise<void> {
    if (session === null) return;
    const storage = await db();
    const done = submitAttempt(session, { value, unit }, webClock);
    await saveAttempt(storage, done);
    await storage.persist();
    setSession(null);
    await loadPast();
    onBack();
  }

  const phase = timerPhase(elapsed, budgetMs);

  return (
    <section className="screen solve">
      <header className="solve__head" data-phase={phase}>
        <TimerRing elapsedMs={elapsed} budgetMs={budgetMs} />
        <span className="solve__divider" aria-hidden="true" />
        <div>
          <div className="mono solve__ordinal">{task.ordinal}</div>
          <h1 className="title-18">{task.title}</h1>
          <div className="solve__meta">
            <PointsBadge points={task.points} />
            <span className="label-10">{task.topic ?? 'OHNE THEMA'}</span>
            <span className="mono small">{Math.round(task.timeBudgetSeconds / 60)} MIN BUDGET</span>
          </div>
        </div>
      </header>

      <div className="solve__grid">
        <div className="panel">
          <h2 className="label-11">AUFGABENSTELLUNG</h2>
          <p className="body-14 muted">
            Der Aufgabentext wird in M1 nicht extrahiert — die Markierung zeigt auf
            Seite {task.pageArtifactId.split(':').pop()} des Originals. Rechne auf Papier
            und trage das Ergebnis ein.
          </p>
          <div className="sketch" aria-hidden="true"><span className="mono">SKIZZENFLÄCHE</span></div>
        </div>

        <div className="panel">
          <h2 className="label-11">ERGEBNIS</h2>
          <UnitInput value={value} unit={unit} onValueChange={setValue} onUnitChange={setUnit} />

          <div className="solve__actions">
            <button type="button" onClick={onBack}>Zurück</button>
            <button type="button" className="primary" data-testid="submit-attempt" onClick={() => void submit()}>
              Abgeben
            </button>
          </div>

          <h2 className="label-11">FRÜHERE VERSUCHE</h2>
          {past.length === 0 ? (
            <p className="body-13 muted">Noch kein abgegebener Versuch.</p>
          ) : (
            <ul className="attempt-list" data-testid="attempt-list">
              {past.map((a) => (
                <li key={a.id} data-testid="attempt-row">
                  <span className="mono" data-testid="attempt-answer">
                    {a.answerValue ?? '—'} {a.answerUnit ?? ''}
                  </span>
                  <span className="mono muted" data-testid="attempt-elapsed">
                    {Math.round(a.elapsedMs / 1000)} s
                  </span>
                  <span className="mono muted">{formatPoints(a.maxPoints)} P möglich</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
