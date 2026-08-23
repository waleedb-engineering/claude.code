import { useEffect, useState } from 'react';
import type { ExamPaper, Task } from '@klausura/model';
import { formatPoints } from '@klausura/model';
import { listExamPapers, listTasks } from '@klausura/storage-sqlite';
import { db } from '../platform/db.js';
import { TaskCard } from '../components/TaskCard.js';

/** Screen 03. In M1 ohne Filter und ohne Beherrschungsgrad — der kommt aus M5. */
export function AtlasScreen({ onOpenTask }: { onOpenTask: (task: Task) => void }) {
  const [papers, setPapers] = useState<ExamPaper[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    void (async () => {
      const storage = await db();
      const ps = await listExamPapers(storage);
      setPapers(ps);
      const all: Task[] = [];
      for (const p of ps) all.push(...(await listTasks(storage, p.id)));
      setTasks(all);
    })();
  }, []);

  const totalPoints = tasks.reduce((a, t) => a + t.points, 0);

  return (
    <section className="screen">
      <header className="atlas__head">
        <h1 className="title-24">Aufgaben-Atlas</h1>
        <span className="mono muted" data-testid="atlas-count">
          {tasks.length} AUFGABEN · {formatPoints(totalPoints)} P
        </span>
      </header>

      {tasks.length === 0 ? (
        <div className="empty">
          <p className="label-10">03 · AUFGABEN-ATLAS</p>
          <h2 className="title-18">Noch keine Aufgabe erfasst</h2>
          <p className="body-14 muted">
            Der Atlas füllt sich, sobald du eine Klausur importiert und mindestens
            eine Aufgabe markiert hast.
          </p>
        </div>
      ) : (
        <div className="card-grid" data-testid="atlas-grid">
          {tasks.map((t) => <TaskCard key={t.id} task={t} onOpen={onOpenTask} />)}
        </div>
      )}

      {papers.length > 0 && (
        <p className="mono muted small">
          {papers.length} KLAUSUR{papers.length === 1 ? '' : 'EN'} IMPORTIERT
        </p>
      )}
    </section>
  );
}
