"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createJob } from "@/lib/api";
import Spinner from "@/components/Spinner";
import Disclaimer from "@/components/Disclaimer";

const ACCEPT = ".mp4,.mov,.mkv,.webm,.avi,.m4v";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [transcript, setTranscript] = useState<File | null>(null);
  const [topN, setTopN] = useState(5);
  const [removeSilence, setRemoveSilence] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pickFile(f: File | null) {
    setError(null);
    setFile(f);
  }

  async function handleSubmit() {
    if (!file) {
      setError("Bitte zuerst ein Video auswählen.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { job_id } = await createJob({ file, topN, transcript, removeSilence });
      router.push(`/jobs/${job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload fehlgeschlagen.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Video hochladen
        </h1>
        <p className="mt-1 text-sm text-neutral-400">
          Wähle ein langes Video. Die Analyse startet automatisch im
          Hintergrund.
        </p>
      </div>

      {/* Drop-Zone */}
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
          const f = e.dataTransfer.files?.[0];
          if (f) pickFile(f);
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
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
        />
        <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-xl bg-neutral-800 text-neutral-300">
          <svg
            className="h-6 w-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              d="M12 16V4m0 0 4 4m-4-4-4 4M4 20h16"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        {file ? (
          <p className="font-medium text-neutral-100">{file.name}</p>
        ) : (
          <>
            <p className="font-medium text-neutral-200">
              Datei hierher ziehen oder klicken
            </p>
            <p className="mt-1 text-xs text-neutral-500">
              MP4, MOV, MKV, WEBM, AVI, M4V
            </p>
          </>
        )}
      </div>

      {/* Optionen */}
      <div className="grid gap-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm text-neutral-300">Anzahl Top-Clips</span>
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
          <span className="text-sm text-neutral-300">
            Transkript (optional, JSON)
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
      </div>

      {/* Silence-Removal-Toggle */}
      <button
        type="button"
        onClick={() => setRemoveSilence((v) => !v)}
        className="flex w-full items-start justify-between gap-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5 text-left transition hover:border-neutral-700"
      >
        <div>
          <p className="font-medium text-neutral-100">
            Stille Pausen automatisch entfernen
          </p>
          <p className="mt-1 text-sm text-neutral-400">
            Macht Clips schneller und dichter. Kann bei sehr leisen Stellen
            manchmal ungenau sein.
          </p>
        </div>
        <span
          role="switch"
          aria-checked={removeSilence}
          className={`mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
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

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting || !file}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 font-medium text-neutral-900 transition hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? (
          <>
            <Spinner className="h-4 w-4" /> Wird hochgeladen …
          </>
        ) : (
          "Analyse starten"
        )}
      </button>

      <Disclaimer />
    </div>
  );
}
