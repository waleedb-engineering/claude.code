import { useState } from 'react';
import {
  asExamPaperId, asPageArtifactId, asSourceDocumentId, asSubjectId,
  pointsFromDecimal,
} from '@klausura/model';
import type { ExamPaperId } from '@klausura/model';
import {
  findDocumentBySha, insertExamPaper, insertPageArtifact,
  insertSourceDocument, upsertSubject,
} from '@klausura/storage-sqlite';
import { parseDecimal } from '@klausura/core';
import { db } from '../platform/db.js';
import { webPdf } from '../platform/web-pdf.js';
import { sha256Hex } from '../platform/sha256.js';
import { putBlob } from '../platform/blobs.js';

const DEFAULT_SUBJECT = asSubjectId('subject-et2');

/**
 * Stufe 1 bis 3 der Ingest-Pipeline (docs/klausura/03): Datei aufnehmen,
 * Seitenmodell erzeugen, Artefakte persistieren. Kein OCR, keine Automatik,
 * kein Netz — M1 ist ausdrücklich ohne KI.
 */
export function ImportScreen({ onImported }: { onImported: (id: ExamPaperId) => void }) {
  const [title, setTitle] = useState('Altklausur 03');
  const [term, setTerm] = useState('WS 2023');
  const [duration, setDuration] = useState('90');
  const [total, setTotal] = useState('90');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const sha = await sha256Hex(bytes);
      const storage = await db();

      const duplicate = await findDocumentBySha(storage, sha);
      if (duplicate !== undefined) {
        setError('Diese Datei wurde bereits importiert. Sie liegt schon im Atlas.');
        return;
      }

      const doc = await webPdf.open(bytes);
      const examId = asExamPaperId(`exam-${sha.slice(0, 12)}`);
      const docId = asSourceDocumentId(`doc-${sha.slice(0, 12)}`);

      await storage.transaction(async () => {
        await upsertSubject(storage, { id: DEFAULT_SUBJECT, name: 'Elektrotechnik 2', code: 'ET2' });
        await insertExamPaper(storage, {
          id: examId, subjectId: DEFAULT_SUBJECT, title, term,
          // parseDecimal statt Number(): die Eingabe ist deutsch, und
          // Number("30,5") ist NaN. Genau dafuer gibt es die Funktion im Kern.
          durationMinutes: parseDecimal(duration) ?? 90,
          totalPoints: pointsFromDecimal(parseDecimal(total) ?? 0),
          passPoints: null, status: 'draft', importedAt: Date.now(),
        });
        await insertSourceDocument(storage, {
          id: docId, examPaperId: examId, role: 'exam', fileName: file.name,
          mimeType: file.type || 'application/pdf', sha256: sha,
          pageCount: doc.pageCount, hasTextLayer: doc.hasTextLayer,
        });
        for (let n = 1; n <= doc.pageCount; n++) {
          const info = await doc.page(n);
          await insertPageArtifact(storage, {
            id: asPageArtifactId(`${docId}:${n}`),
            sourceDocumentId: docId, pageNumber: n,
            widthPt: info.widthPt, heightPt: info.heightPt,
          });
        }
      });

      await putBlob(`pdf:${examId}`, bytes);
      await storage.persist();
      await doc.close();
      onImported(examId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Die Datei liess sich nicht lesen.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screen">
      <h1 className="title-24">Altklausur importieren</h1>
      <p className="body-14 muted">
        PDF wählen. Die Zerlegung machst du im nächsten Schritt selbst — in M1 gibt es
        bewusst keine Automatik, damit die App schon Nutzen hat, bevor sie rät.
      </p>

      <div className="form-grid">
        <label className="label-11" htmlFor="f-title">TITEL</label>
        <input id="f-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="label-11" htmlFor="f-term">SEMESTER</label>
        <input id="f-term" value={term} onChange={(e) => setTerm(e.target.value)} />
        <label className="label-11" htmlFor="f-duration">DAUER IN MINUTEN</label>
        <input id="f-duration" data-testid="exam-duration" inputMode="numeric"
               value={duration} onChange={(e) => setDuration(e.target.value)} />
        <label className="label-11" htmlFor="f-total">GESAMTPUNKTE</label>
        <input id="f-total" data-testid="exam-total" inputMode="decimal"
               value={total} onChange={(e) => setTotal(e.target.value)} />
      </div>

      <div className="dropzone">
        <input
          type="file" accept="application/pdf" data-testid="pdf-input" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }}
        />
        <p className="body-13 muted">{busy ? 'Wird gelesen …' : 'PDF auswählen'}</p>
      </div>

      {error !== null && <p className="notice notice--over" data-testid="import-error">{error}</p>}
    </section>
  );
}
