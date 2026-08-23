import { useCallback, useEffect, useRef, useState } from 'react';
import { asSegmentOverrideId, asTaskId, checkRectWithinPage, pointsFromDecimal } from '@klausura/model';
import type { ExamPaper, ExamPaperId, NormRect, PageArtifact, SegmentOverride, Task } from '@klausura/model';
import { distributeTimeBudget, mergeSegmentation, parseDecimal, pointSumStatus } from '@klausura/core';
import {
  getExamPaper, insertOverride, listOverrides, listPageArtifacts,
  replaceTasks, setExamPaperStatus,
} from '@klausura/storage-sqlite';
import { db } from '../platform/db.js';
import { webPdf } from '../platform/web-pdf.js';
import { getBlob } from '../platform/blobs.js';
import { PointsBadge } from '../components/PointsBadge.js';

const PAGE_WIDTH_PX = 620;

interface Draft { readonly rect: NormRect; readonly page: PageArtifact }

/**
 * Manuelle Segmentierung (M1). Der Nutzer zieht einen Rahmen und vergibt
 * Nummer, Punkte und Thema.
 *
 * Jede Eingabe wird als SegmentOverride gespeichert, nicht als Aufgabe. Die
 * Aufgaben werden daraus abgeleitet. Das ist Invariante I12: wenn ab M3 eine
 * Automatik dazukommt, kann sie diese Korrekturen konstruktiv nicht
 * überschreiben — die Korrektur ist die Basis, der Vorschlag der Zusatz.
 */
export function SegmentScreen({ examId, onDone }: { examId: ExamPaperId; onDone: () => void }) {
  const [exam, setExam] = useState<ExamPaper | null>(null);
  const [pages, setPages] = useState<PageArtifact[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [overrides, setOverrides] = useState<SegmentOverride[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [ordinal, setOrdinal] = useState('A1');
  const [points, setPoints] = useState('8,5');
  const [topic, setTopic] = useState('');
  const [error, setError] = useState<string | null>(null);

  const canvasHost = useRef<HTMLDivElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    void (async () => {
      const storage = await db();
      const paper = await getExamPaper(storage, examId);
      setExam(paper ?? null);
      const docId = `doc-${String(examId).slice('exam-'.length)}`;
      const ps = await listPageArtifacts(storage, docId as PageArtifact['sourceDocumentId']);
      setPages(ps);
      setOverrides(await listOverrides(storage, ps.map((p) => p.id)));
    })();
  }, [examId]);

  const page = pages[pageIndex];

  // Seite rendern. Nur bei Seitenwechsel, nicht bei jeder Zustandsänderung —
  // sonst kostet jeder Tastendruck ein komplettes Neurendern.
  useEffect(() => {
    if (page === undefined) return;
    let cancelled = false;
    void (async () => {
      const bytes = await getBlob(`pdf:${examId}`);
      if (bytes === undefined || cancelled) return;
      const doc = await webPdf.open(bytes);
      const canvas = await doc.renderToCanvas(page.pageNumber, PAGE_WIDTH_PX);
      if (cancelled) { await doc.close(); return; }
      const host = canvasHost.current;
      if (host !== null) {
        host.replaceChildren(canvas);
        canvas.className = 'page-canvas';
      }
      await doc.close();
    })();
    return () => { cancelled = true; };
  }, [examId, page]);

  const merged = mergeSegmentation([], overrides);
  const sum = pointSumStatus(merged.map((m) => m.points), exam?.totalPoints ?? 0);

  const toNorm = useCallback((e: React.PointerEvent<HTMLDivElement>): { x: number; y: number } => {
    const box = e.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - box.left) / box.width)),
      y: Math.min(1, Math.max(0, (e.clientY - box.top) / box.height)),
    };
  }, []);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    if (page === undefined) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragStart.current = toNorm(e);
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>): void {
    const start = dragStart.current;
    if (start === null || page === undefined) return;
    const now = toNorm(e);
    setDraft({
      page,
      rect: {
        x: Math.min(start.x, now.x), y: Math.min(start.y, now.y),
        width: Math.abs(now.x - start.x), height: Math.abs(now.y - start.y),
      },
    });
  }

  function onPointerUp(): void { dragStart.current = null; }

  /** Auch per Tastatur erreichbar: ein Rahmen über die ganze Seite. */
  function addFullPageDraft(): void {
    if (page === undefined) return;
    setDraft({ page, rect: { x: 0.05, y: 0.05, width: 0.9, height: 0.4 } });
  }

  async function saveDraft(): Promise<void> {
    if (draft === null) { setError('Erst einen Rahmen ziehen.'); return; }
    const violations = checkRectWithinPage(draft.rect);
    if (violations.length > 0) { setError(violations[0]?.message ?? 'Ungültige Markierung.'); return; }
    const value = parseDecimal(points);
    if (value === null || value <= 0) { setError('Punkte müssen eine positive Zahl sein.'); return; }
    if (ordinal.trim() === '') { setError('Die Aufgabe braucht eine Nummer.'); return; }

    const storage = await db();
    const record: SegmentOverride = {
      id: asSegmentOverrideId(`ovr-${draft.page.id}-${ordinal}-${Date.now()}`),
      pageArtifactId: draft.page.id,
      action: 'create',
      ordinal: ordinal.trim(),
      points: pointsFromDecimal(value),
      topic: topic.trim() === '' ? null : topic.trim(),
      rect: draft.rect,
      createdAt: Date.now(),
    };
    await insertOverride(storage, record);
    await storage.persist();

    setOverrides((prev) => [...prev, record]);
    setDraft(null);
    setError(null);
    setOrdinal(nextOrdinal(ordinal));
    setTopic('');
  }

  async function finish(): Promise<void> {
    if (exam === null) return;
    const storage = await db();
    const budgets = distributeTimeBudget(
      merged.map((m) => m.points), exam.totalPoints, exam.durationMinutes,
    );
    const tasks: Task[] = merged.map((m, i) => ({
      id: asTaskId(`${examId}:${m.ordinal}`),
      examPaperId: examId,
      ordinal: m.ordinal,
      title: `Aufgabe ${m.ordinal}`,
      points: m.points,
      timeBudgetSeconds: budgets[i] ?? 0,
      kind: 'calculation',
      topic: m.topic,
      pageArtifactId: m.pageArtifactId,
      rect: m.rect,
    }));
    await replaceTasks(storage, examId, tasks);
    await setExamPaperStatus(storage, examId, 'ready');
    await storage.persist();
    onDone();
  }

  return (
    <section className="screen segment">
      <header className="segment__head">
        <h1 className="title-24">{exam?.title ?? 'Zerlegen'}</h1>
        <p className="body-13 muted">
          Rahmen ziehen, Nummer und Punkte vergeben. Jede Eingabe ist eine Korrektur und
          überlebt jede spätere Automatik.
        </p>
      </header>

      <div className="segment__grid">
        <div>
          <div className="segment__pagebar">
            <button type="button" onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                    disabled={pageIndex === 0}>Zurück</button>
            <span className="mono" data-testid="page-indicator">
              SEITE {page?.pageNumber ?? 0} VON {pages.length}
            </span>
            <button type="button" onClick={() => setPageIndex((i) => Math.min(pages.length - 1, i + 1))}
                    disabled={pageIndex >= pages.length - 1}>Weiter</button>
          </div>

          <div
            className="page-frame"
            data-testid="page-frame"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            <div ref={canvasHost} className="page-canvas-host" />
            {overrides
              .filter((o) => o.pageArtifactId === page?.id)
              .map((o) => (
                <span key={o.id} className="marking" style={rectStyle(o.rect)}>
                  <span className="marking__tag mono">{o.ordinal}</span>
                </span>
              ))}
            {draft !== null && draft.page.id === page?.id && (
              <span className="marking marking--draft" data-testid="draft-rect" style={rectStyle(draft.rect)} />
            )}
          </div>
        </div>

        <aside className="segment__side">
          <h2 className="label-11">NEUE AUFGABE</h2>
          <button type="button" onClick={addFullPageDraft} data-testid="draft-keyboard">
            Rahmen ohne Maus setzen
          </button>

          <label className="label-11" htmlFor="s-ordinal">NUMMER</label>
          <input id="s-ordinal" data-testid="seg-ordinal" value={ordinal}
                 onChange={(e) => setOrdinal(e.target.value)} />

          <label className="label-11" htmlFor="s-points">PUNKTE</label>
          <input id="s-points" data-testid="seg-points" inputMode="decimal" value={points}
                 onChange={(e) => setPoints(e.target.value)} />

          <label className="label-11" htmlFor="s-topic">THEMA</label>
          <input id="s-topic" data-testid="seg-topic" value={topic}
                 onChange={(e) => setTopic(e.target.value)} />

          <button type="button" className="primary" data-testid="seg-save" onClick={() => void saveDraft()}>
            Aufgabe übernehmen
          </button>
          {error !== null && <p className="notice notice--over" data-testid="seg-error">{error}</p>}

          <h2 className="label-11">ERFASST</h2>
          <ul className="seg-list" data-testid="seg-list">
            {merged.map((m) => (
              <li key={m.ordinal}>
                <span className="mono">{m.ordinal}</span>
                <span className="body-13 muted">{m.topic ?? 'ohne Thema'}</span>
                <PointsBadge points={m.points} />
              </li>
            ))}
          </ul>

          <p className={`sum sum--${sum.kind}`} data-testid="point-sum">{sum.message}</p>

          <button type="button" className="primary" data-testid="seg-finish"
                  disabled={merged.length === 0} onClick={() => void finish()}>
            Fertig — zum Atlas
          </button>
        </aside>
      </div>
    </section>
  );
}

function rectStyle(r: NormRect): React.CSSProperties {
  return {
    left: `${r.x * 100}%`, top: `${r.y * 100}%`,
    width: `${r.width * 100}%`, height: `${r.height * 100}%`,
  };
}

/** A1 → A2, A9 → A10. Spart Tippen bei der Zerlegung. */
function nextOrdinal(current: string): string {
  const m = /^(\D*)(\d+)$/.exec(current.trim());
  if (m === null) return current;
  return `${m[1] ?? ''}${Number(m[2]) + 1}`;
}
