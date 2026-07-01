"use client";

import { useState } from "react";
import type { StorageSummary } from "@/lib/types";
import { bulkDeleteJobs } from "@/lib/api";

const STATUS_LABELS: { key: string; label: string }[] = [
  { key: "completed", label: "Fertig" },
  { key: "failed", label: "Fehlgeschlagen" },
  { key: "interrupted", label: "Unterbrochen" },
  { key: "incomplete", label: "Unvollständig" },
  { key: "processing", label: "Läuft" },
  { key: "queued", label: "Warteschlange" },
];

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-neutral-500">
        {label}
      </p>
      <p className="font-semibold text-neutral-100">{value}</p>
    </div>
  );
}

export default function StorageWidget({
  storage,
  onCleaned,
}: {
  storage: StorageSummary | null;
  /** Wird nach erfolgreichem Bulk-Cleanup aufgerufen (Listen neu laden). */
  onCleaned?: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  if (!storage) return null;

  const cc = storage.cleanup_candidates;
  // completed_without_exports gehört BEWUSST NICHT zum Auto-Cleanup.
  const problemIds = [...cc.failed, ...cc.interrupted, ...cc.incomplete];
  const nProblem = problemIds.length;

  async function runCleanup() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await bulkDeleteJobs(problemIds, "DELETE");
      setResult(
        `${r.deleted_count} gelöscht${
          r.failed_count ? `, ${r.failed_count} fehlgeschlagen` : ""
        } · ${r.removed_human} freigegeben`,
      );
      setConfirming(false);
      onCleaned?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cleanup fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const largest = storage.largest_jobs.slice(0, 3);

  return (
    <section className="space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-6">
          <Metric label="Lokaler Speicher" value={storage.total_human} />
          <Metric label="Jobs" value={String(storage.total_jobs)} />
          <Metric label="Auto-Exports" value={String(storage.counts.auto_exports)} />
          <Metric
            label="Manuelle Exporte"
            value={String(storage.counts.manual_exports)}
          />
        </div>

        {/* Bulk-Cleanup */}
        <div className="flex flex-col items-end gap-1">
          {!confirming ? (
            <button
              type="button"
              disabled={nProblem === 0}
              onClick={() => setConfirming(true)}
              title={
                nProblem === 0
                  ? "Keine problematischen Jobs zum Aufräumen"
                  : undefined
              }
              className="rounded-lg border border-amber-500/30 px-3 py-2 text-sm font-medium text-amber-300 transition hover:border-amber-500/60 hover:bg-amber-500/10 disabled:cursor-not-allowed disabled:border-neutral-800 disabled:text-neutral-600 disabled:hover:bg-transparent"
            >
              Problematische Jobs aufräumen
              {nProblem > 0 ? ` (${nProblem})` : ""}
            </button>
          ) : (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="text-xs text-neutral-300">
                Wirklich alle fehlgeschlagenen, unterbrochenen und
                unvollständigen Jobs löschen?
              </span>
              <button
                type="button"
                onClick={runCleanup}
                disabled={busy}
                className="rounded-lg bg-rose-500/90 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-rose-500 disabled:opacity-50"
              >
                {busy ? "Räume auf …" : `Ja, ${nProblem} löschen`}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={busy}
                className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
              >
                Abbrechen
              </button>
            </div>
          )}
          {nProblem === 0 && !result && (
            <span className="text-[11px] text-neutral-600">
              Keine problematischen Jobs zum Aufräumen
            </span>
          )}
          {result && <span className="text-[11px] text-emerald-400">{result}</span>}
          {error && <span className="text-[11px] text-rose-400">{error}</span>}
        </div>
      </div>

      {/* Status-Verteilung */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
        {STATUS_LABELS.map(({ key, label }) => (
          <span key={key}>
            {label}:{" "}
            <span className="text-neutral-200">
              {storage.by_status[key] ?? 0}
            </span>
          </span>
        ))}
      </div>

      {/* Größte Jobs */}
      {largest.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-wide text-neutral-500">
            Größte Jobs
          </p>
          <ul className="space-y-1">
            {largest.map((j) => (
              <li
                key={j.job_id}
                className="flex items-center justify-between gap-3 text-xs text-neutral-400"
              >
                <span className="min-w-0 truncate">
                  {j.filename}{" "}
                  <span className="text-neutral-600">· {j.job_id}</span>
                </span>
                <span className="shrink-0 tabular-nums text-neutral-300">
                  {j.human_size}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
