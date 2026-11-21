"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, studio, type WeightCompare } from "@/lib/studio";
import { ErrorBox, btnCls, cardCls, primaryCls } from "@/components/studio/ui";

function pct(v: number | null | undefined) {
  return v == null ? "–" : `${Math.round(v * 100)} %`;
}

/** Auswertung der Highlight-Erkennung über alle vom Nutzer markierten Streams. */
export default function StreamEvaluationPage() {
  const [data, setData] = useState<WeightCompare | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tune, setTune] = useState<Awaited<ReturnType<typeof studio.tuneStreamWeights>> | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await studio.compareStreamWeights();
      setMissing(d.streams.length === 0);
      setData(d.streams.length ? d : null);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Highlight-Erkennung auswerten</h1>
        <p className="text-sm text-neutral-400">
          Vergleicht die automatisch gefundenen Highlights mit deinen Markierungen. Nur echte, eigene Aufnahmen sagen etwas über die Qualität aus.
        </p>
      </div>
      <ErrorBox message={error} />
      {missing && (
        <section className={`${cardCls} space-y-2 text-sm text-neutral-300`} aria-label="So geht's">
          <p className="font-medium text-white">Noch keine markierten Streams.</p>
          <ol className="list-decimal space-y-1 pl-5">
            <li>Eigenes VOD (Twitch-Dashboard → Videoproduzent → Herunterladen bzw. YouTube Studio) unter „Streams“ hochladen.</li>
            <li>Chat-Export dazu laden (TwitchDownloader → JSON bzw. chat-downloader für YouTube).</li>
            <li>„Highlights finden“, dann jedes Highlight mit „✓ echtes Highlight“ / „✗ kein Highlight“ markieren und verpasste Momente ergänzen.</li>
            <li>Mindestens zwei Streams so markieren — dann hier vergleichen und Gewichte schätzen.</li>
          </ol>
          <Link href="/studio/streams" className={primaryCls}>
            Zu den Streams
          </Link>
        </section>
      )}
      {data && (
        <>
          <section className={cardCls} aria-label="Vergleich">
            <table className="w-full text-left text-sm" data-testid="eval-table">
              <thead className="text-xs text-neutral-400">
                <tr>
                  <th className="py-1">Stream</th>
                  <th>Markiert</th>
                  <th>F1 Standard</th>
                  <th>F1 aktuell</th>
                  <th>Präzision / Recall (aktuell)</th>
                  <th>Duplikate</th>
                </tr>
              </thead>
              <tbody className="text-neutral-200">
                {data.streams.map((s) => (
                  <tr key={s.id} className="border-t border-neutral-800">
                    <td className="py-1">
                      <Link href={`/studio/streams/${s.id}`} className="hover:underline">
                        {s.name}
                      </Link>
                      {s.synthetic ? <span className="ml-1 text-xs text-amber-300">synthetisch</span> : null}
                    </td>
                    <td>{s.labels}</td>
                    <td>{pct(s.default.f1)}</td>
                    <td>{pct(s.current.f1)}</td>
                    <td>
                      {pct(s.current.precision)} / {pct(s.current.recall)}
                    </td>
                    <td>{s.current.duplicates}</td>
                  </tr>
                ))}
                <tr className="border-t border-neutral-700 font-medium">
                  <td className="py-1">Gesamt ({data.real_streams} echte)</td>
                  <td />
                  <td>{pct(data.total_default.f1)}</td>
                  <td>{pct(data.total_current.f1)}</td>
                  <td>
                    {pct(data.total_current.precision)} / {pct(data.total_current.recall)}
                  </td>
                  <td>{data.total_current.duplicates}</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-xs text-neutral-500">{data.note}</p>
          </section>
          <section className={`${cardCls} space-y-2`} aria-label="Gewichte">
            <p className="text-sm text-neutral-200">
              Aktive Gewichte: {data.tuned ? `eigene (übernommen ${data.tuned.at ?? ""})` : "Standard"} · Historie: {data.history.length} Einträge
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={btnCls} disabled={busy} onClick={() => void run(async () => setTune(await studio.tuneStreamWeights(false)))}>
                Gewichte schätzen
              </button>
              {tune && !tune.applied && (
                <button type="button" className={primaryCls} disabled={busy} onClick={() => void run(async () => setTune(await studio.tuneStreamWeights(true)))}>
                  Übernehmen (nur bei Verbesserung)
                </button>
              )}
              <button type="button" className={btnCls} disabled={busy || data.history.length === 0} onClick={() => void run(() => studio.rollbackStreamWeights())}>
                ↶ Vorherige Gewichte
              </button>
              <button type="button" className={btnCls} disabled={busy || !data.tuned} onClick={() => void run(() => studio.resetStreamWeights())}>
                Auf Standard zurück
              </button>
            </div>
            {tune && (
              <p className="text-xs text-neutral-300" data-testid="eval-tune">
                F1 Standard {pct(tune.f1_default)} · getunt {pct(tune.f1_tuned)} · Kreuzprüfung {pct(tune.f1_leave_one_out)} · Faktoren{" "}
                {Object.entries(tune.best_group_factors)
                  .map(([k, v]) => `${k} ×${v}`)
                  .join(", ")}
                {tune.applied ? " · übernommen" : ""}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
