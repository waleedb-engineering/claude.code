"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { batchUpload, createJob } from "@/lib/api";
import type { BatchUploadRow } from "@/lib/types";
import Spinner from "@/components/Spinner";
import Disclaimer from "@/components/Disclaimer";

const ACCEPT = ".mp4,.mov,.mkv,.webm,.avi,.m4v";

type RowStatus = "wartet" | "laedt" | "angenommen" | "fehler";
interface Row {
  file: File;
  status: RowStatus;
  jobId?: string | null;
  error?: string | null;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const STATUS_STYLE: Record<RowStatus, string> = {
  wartet: "text-neutral-500",
  laedt: "text-indigo-300",
  angenommen: "text-emerald-400",
  fehler: "text-rose-400",
};
const STATUS_LABEL: Record<RowStatus, string> = {
  wartet: "Wartet",
  laedt: "Lädt hoch …",
  angenommen: "Angenommen",
  fehler: "Fehler",
};

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [rows, setRows] = useState<Row[]>([]);
  const [transcript, setTranscript] = useState<File | null>(null);
  const [topN, setTopN] = useState(5);
  const [removeSilence, setRemoveSilence] = useState(true);
  const [captionStyle, setCaptionStyle] = useState("high_energy");
  const [reframeMode, setReframeMode] = useState("smart");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function addFiles(list: FileList | null) {
    if (!list) return;
    setError(null);
    setDone(false);
    const next = Array.from(list).map((file) => ({
      file,
      status: "wartet" as RowStatus,
    }));
    setRows((prev) => [...prev, ...next]);
  }

  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function handleSubmit() {
    if (rows.length === 0) {
      setError("Bitte zuerst mindestens ein Video auswählen.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setRows((prev) => prev.map((r) => ({ ...r, status: "laedt" })));

    try {
      if (rows.length === 1) {
        // Einzel-Upload (mit optionalem Transkript) — unverändertes Verhalten.
        try {
          const { job_id } = await createJob({
            file: rows[0].file,
            topN,
            transcript,
            removeSilence,
            captionStyle,
            reframeMode,
          });
          setRows([{ ...rows[0], status: "angenommen", jobId: job_id }]);
        } catch (e) {
          setRows([
            {
              ...rows[0],
              status: "fehler",
              error: e instanceof Error ? e.message : "Upload fehlgeschlagen.",
            },
          ]);
        }
      } else {
        // Batch-Upload: ein Request, Ergebnis pro Datei (Reihenfolge = Sendereihenfolge).
        const res = await batchUpload({
          files: rows.map((r) => r.file),
          topN,
          removeSilence,
          captionStyle,
          reframeMode,
        });
        setRows((prev) =>
          prev.map((r, i) => {
            const out: BatchUploadRow | undefined = res.results[i];
            if (!out) return { ...r, status: "fehler", error: "Kein Ergebnis." };
            return {
              ...r,
              status: out.accepted ? "angenommen" : "fehler",
              jobId: out.job_id,
              error: out.error,
            };
          }),
        );
      }
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload fehlgeschlagen.");
      setRows((prev) => prev.map((r) => ({ ...r, status: "wartet" })));
    } finally {
      setSubmitting(false);
    }
  }

  const acceptedCount = rows.filter((r) => r.status === "angenommen").length;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Videos hochladen
        </h1>
        <p className="mt-1 text-sm text-neutral-400">
          Ein oder mehrere Videos wählen. Jede Datei wird zu einem eigenen Job;
          die Analyse startet automatisch im Hintergrund.
        </p>
      </div>

      {/* Drop-Zone (mehrere Dateien) */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition ${
          dragging
            ? "border-indigo-400 bg-indigo-500/5"
            : "border-neutral-700 hover:border-neutral-600 bg-neutral-900/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
        <p className="font-medium text-neutral-200">
          Dateien hierher ziehen oder klicken
        </p>
        <p className="mt-1 text-xs text-neutral-500">
          Mehrfachauswahl möglich · MP4, MOV, MKV, WEBM, AVI, M4V
        </p>
      </div>

      {/* Datei-Liste */}
      {rows.length > 0 && (
        <div className="space-y-2 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-neutral-200">
              {rows.length} Datei{rows.length === 1 ? "" : "en"}
            </p>
            {!submitting && !done && (
              <button
                type="button"
                onClick={() => setRows([])}
                className="text-xs text-neutral-500 hover:text-neutral-300"
              >
                Liste leeren
              </button>
            )}
          </div>
          <ul className="space-y-1.5">
            {rows.map((r, i) => (
              <li
                key={i}
                className="flex items-center justify-between gap-3 rounded-lg bg-neutral-800/40 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-neutral-100">
                    {r.file.name}
                  </p>
                  <p className="text-[11px] text-neutral-500">
                    {fmtSize(r.file.size)}
                    {r.error ? ` · ${r.error}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className={`text-xs ${STATUS_STYLE[r.status]}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                  {r.status === "angenommen" && r.jobId && (
                    <Link
                      href={`/jobs/${r.jobId}`}
                      className="rounded-md border border-neutral-700 px-2 py-1 text-[11px] text-neutral-200 transition hover:border-neutral-500 hover:text-white"
                    >
                      Job öffnen
                    </Link>
                  )}
                  {!submitting && !done && (
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      className="text-neutral-600 hover:text-neutral-300"
                      aria-label="Entfernen"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Gemeinsame Optionen */}
      <div className="grid gap-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm text-neutral-300">Top-Clips je Video</span>
          <input
            type="number"
            min={1}
            max={20}
            value={topN}
            onChange={(e) => setTopN(Math.max(1, Number(e.target.value) || 1))}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="text-sm text-neutral-300">Caption-Style</span>
          <select
            value={captionStyle}
            onChange={(e) => setCaptionStyle(e.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          >
            <option value="high_energy">High Energy</option>
            <option value="clean">Clean</option>
          </select>
        </label>
        <label className="block">
          <span className="text-sm text-neutral-300">Bildausrichtung</span>
          <select
            value={reframeMode}
            onChange={(e) => setReframeMode(e.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          >
            <option value="smart">Automatisch / Smart</option>
            <option value="face">Gesicht / Face</option>
            <option value="center">Mitte / Center</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setRemoveSilence((v) => !v)}
          className="flex items-center justify-between gap-3 self-end rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-left"
        >
          <span className="text-sm text-neutral-300">
            Stille Pausen entfernen
          </span>
          <span
            role="switch"
            aria-checked={removeSilence}
            className={`inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
              removeSilence ? "bg-indigo-500" : "bg-neutral-700"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                removeSilence ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </span>
        </button>
      </div>

      {/* Transkript nur bei genau 1 Datei (deterministischer Einzel-Upload) */}
      {rows.length === 1 && (
        <label className="block rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
          <span className="text-sm text-neutral-300">
            Transkript (optional, JSON — nur Einzel-Upload)
          </span>
          <input
            type="file"
            accept=".json"
            onChange={(e) => setTranscript(e.target.files?.[0] ?? null)}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-400 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-800 file:px-2 file:py-1 file:text-neutral-200"
          />
          <span className="mt-1 block text-[11px] text-neutral-500">
            Überspringt die lokale Transkription (schneller/deterministisch).
          </span>
        </label>
      )}

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Ergebnis-Aktionen nach Upload */}
      {done ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-900/40 px-4 py-3">
          <span className="text-sm text-neutral-300">
            {acceptedCount} Job{acceptedCount === 1 ? "" : "s"} angelegt.
          </span>
          <Link
            href="/jobs"
            className="rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-neutral-900 transition hover:bg-neutral-200"
          >
            Zur Queue
          </Link>
          {acceptedCount === 1 && (
            <button
              type="button"
              onClick={() => {
                const j = rows.find((r) => r.jobId)?.jobId;
                if (j) router.push(`/jobs/${j}`);
              }}
              className="rounded-lg border border-neutral-700 px-3.5 py-2 text-sm text-neutral-200 transition hover:border-neutral-500"
            >
              Job öffnen
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setRows([]);
              setTranscript(null);
              setDone(false);
            }}
            className="text-sm text-neutral-500 hover:text-neutral-300"
          >
            Weitere hochladen
          </button>
        </div>
      ) : (
        <button
          onClick={handleSubmit}
          disabled={submitting || rows.length === 0}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 font-medium text-neutral-900 transition hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? (
            <>
              <Spinner className="h-4 w-4" /> Wird hochgeladen …
            </>
          ) : (
            "Videos analysieren"
          )}
        </button>
      )}

      <Disclaimer />
    </div>
  );
}
