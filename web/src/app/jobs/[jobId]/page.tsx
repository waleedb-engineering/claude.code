"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  allExportsZipUrl,
  exportsZipUrl,
  getClips,
  getJob,
  getManualExports,
} from "@/lib/api";
import type { ClipsJson, Job, ManualExport } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import Spinner from "@/components/Spinner";
import ClipCard from "@/components/ClipCard";
import Disclaimer from "@/components/Disclaimer";
import ManualExportsSection from "@/components/ManualExportsSection";

const POLL_MS = 2000;

export default function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<Job | null>(null);
  const [clips, setClips] = useState<ClipsJson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manualCounts, setManualCounts] = useState<Record<number, number>>({});
  const [manualExports, setManualExports] = useState<ManualExport[]>([]);
  const clipsLoaded = useRef(false);

  const fetchClips = useCallback(async () => {
    if (clipsLoaded.current) return;
    clipsLoaded.current = true;
    try {
      setClips(await getClips(jobId));
    } catch {
      /* clips.json evtl. nicht vorhanden (leeres Ergebnis) — kein harter Fehler */
    }
    try {
      const exports = await getManualExports(jobId);
      setManualExports(exports);
      const counts: Record<number, number> = {};
      for (const e of exports) {
        counts[e.source_clip_index] = (counts[e.source_clip_index] ?? 0) + 1;
      }
      setManualCounts(counts);
    } catch {
      /* manuelle Exporte optional — kein harter Fehler */
    }
  }, [jobId]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const j = await getJob(jobId);
        if (!active) return;
        setJob(j);
        setError(null);
        if (j.status === "completed") {
          await fetchClips();
          return; // Polling stoppen
        }
        if (j.status === "failed") return; // Polling stoppen
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Job konnte nicht geladen werden.");
      }
      timer = setTimeout(tick, POLL_MS);
    }

    tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId, fetchClips]);

  const result = job?.result;
  const downloadableByIndex = new Map(
    (result?.clips ?? []).map((c) => [c.index, c.downloadable]),
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            href="/jobs"
            className="text-xs text-neutral-500 hover:text-neutral-300"
          >
            ← Alle Jobs
          </Link>
          <h1 className="mt-1 truncate text-2xl font-bold tracking-tight text-white">
            {job?.filename ?? "Job"}
          </h1>
          <p className="mt-0.5 font-mono text-xs text-neutral-500">{jobId}</p>
          {job?.restored && (
            <p className="mt-1 text-xs text-neutral-500">
              ↻ Aus lokalem Speicher wiederhergestellt
            </p>
          )}
        </div>
        {job && <StatusBadge status={job.status} />}
      </div>

      {/* Verbindungsfehler */}
      {error && !job && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Wiederhergestellt: unterbrochen / unvollständig */}
      {(job?.status === "interrupted" || job?.status === "incomplete") && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          <p className="font-medium">
            {job.status === "interrupted"
              ? "Job wurde unterbrochen"
              : "Ergebnis unvollständig"}
          </p>
          <p className="mt-1 text-amber-200/80">
            {job.restore_warning ??
              (job.status === "interrupted"
                ? "Dieser Job war beim Server-Neustart aktiv und wurde nicht automatisch fortgesetzt. Bitte das Video erneut hochladen."
                : "Für diesen Job fehlen Ergebnis-Dateien (clips.json oder gerenderte Clips). Es stehen keine Downloads bereit.")}
          </p>
        </div>
      )}

      {/* Initial-Loading */}
      {!job && !error && (
        <div className="flex items-center gap-2 text-sm text-neutral-400">
          <Spinner className="h-4 w-4" /> Lade Job …
        </div>
      )}

      {/* Job-Fehlerstatus */}
      {job?.status === "failed" && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          <p className="font-medium">Analyse fehlgeschlagen</p>
          <p className="mt-1 text-rose-200/80">{job.error}</p>
        </div>
      )}

      {/* Fortschritt / Logs */}
      {job && (job.status === "queued" || job.status === "processing") && (
        <div className="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5">
          <div className="mb-3 flex items-center gap-2 text-sm text-neutral-300">
            <Spinner className="h-4 w-4 text-indigo-400" />
            Analyse läuft — diese Seite aktualisiert sich automatisch.
          </div>
          <ProgressLog lines={job.progress} live />
        </div>
      )}

      {/* Abgeschlossen: Logs einklappbar + Ergebnis */}
      {job?.status === "completed" && (
        <>
          {result?.warning && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
              {result.warning}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 px-5 py-4 text-sm">
            <div className="flex flex-wrap items-center gap-5">
              <Stat
                label="Clips erkannt"
                value={String(job.files?.clip_count ?? result?.clip_count ?? 0)}
              />
              <Stat
                label="Auto-Clips"
                value={String(
                  job.files?.auto_export_count ??
                    job.files?.mp4_count ??
                    result?.rendered_count ??
                    0,
                )}
              />
              <Stat
                label="Manuelle Exporte"
                value={String(job.files?.manual_export_count ?? 0)}
              />
              <Stat
                label="Gesamt-Exporte"
                value={String(
                  job.files?.total_export_count ??
                    job.files?.mp4_count ??
                    0,
                )}
              />
              <Stat label="Sprache" value={result?.language ?? "—"} />
              <Stat
                label="Quell-Länge"
                value={result ? `${Math.round(result.duration)}s` : "—"}
              />
              <Stat
                label="Downloads"
                value={job.files?.exports_ready ? "bereit" : "—"}
              />
              <Stat
                label="Stille-Schnitt"
                value={job.remove_silence ? "an" : "aus"}
              />
              <Stat
                label="Captions"
                value={
                  job.caption_mode === "karaoke" ? "Wortgenau" : "Standard"
                }
              />
              <Stat
                label="Bildausrichtung"
                value={
                  job.reframe_mode === "center"
                    ? "Center"
                    : job.reframe_mode === "face"
                      ? "Face"
                      : "Smart"
                }
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {job.files?.exports_ready && (
                <a
                  href={exportsZipUrl(jobId)}
                  className="inline-flex items-center gap-2 rounded-lg border border-neutral-700 px-3.5 py-2 text-sm font-medium text-neutral-200 transition hover:border-neutral-500 hover:text-white"
                  download
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path
                      d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Alle Clips als ZIP
                </a>
              )}
              {(job.files?.all_exports_ready ?? job.files?.exports_ready) && (
                <a
                  href={allExportsZipUrl(jobId)}
                  className="inline-flex items-center gap-2 rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-neutral-900 transition hover:bg-neutral-200"
                  download
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path
                      d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Alle Exporte als ZIP
                </a>
              )}
            </div>
          </div>

          <details className="rounded-2xl border border-neutral-800 bg-neutral-900/40">
            <summary className="cursor-pointer px-5 py-3 text-sm text-neutral-300">
              Verlauf / Logs anzeigen
            </summary>
            <div className="px-5 pb-4">
              <ProgressLog lines={job.progress} />
            </div>
          </details>

          {/* Clip-Karten */}
          {clips && clips.clips.length > 0 ? (
            <div className="space-y-4">
              <Disclaimer text={clips.disclaimer} />
              <div className="grid gap-4 sm:grid-cols-2">
                {clips.clips.map((c, i) => (
                  <ClipCard
                    key={i}
                    clip={c}
                    index={i + 1}
                    jobId={jobId}
                    downloadable={downloadableByIndex.get(i + 1) ?? false}
                    manualExportCount={manualCounts[i + 1] ?? 0}
                  />
                ))}
              </div>
            </div>
          ) : (
            !result?.warning && (
              <div className="rounded-2xl border border-dashed border-neutral-800 bg-neutral-900/30 p-8 text-center text-sm text-neutral-400">
                Keine Clips zum Anzeigen.
              </div>
            )
          )}

          <ManualExportsSection jobId={jobId} exports={manualExports} />
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-neutral-500">
        {label}
      </p>
      <p className="font-semibold text-neutral-100">{value}</p>
    </div>
  );
}

function ProgressLog({ lines, live }: { lines: string[]; live?: boolean }) {
  if (!lines || lines.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        {live ? "Warte auf erste Ausgabe …" : "Keine Logs."}
      </p>
    );
  }
  return (
    <ol className="space-y-1.5 font-mono text-xs">
      {lines.map((l, i) => (
        <li key={i} className="flex gap-2 text-neutral-400">
          <span className="select-none text-neutral-600">
            {String(i + 1).padStart(2, "0")}
          </span>
          <span className={l.startsWith("FEHLER") ? "text-rose-300" : ""}>
            {l}
          </span>
        </li>
      ))}
    </ol>
  );
}
