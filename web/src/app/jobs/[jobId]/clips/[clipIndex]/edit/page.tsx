"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  clipPreviewUrl,
  getBrandKit,
  getCaptionStyles,
  getClips,
  getManualExports,
  manualExportDownloadUrl,
  manualExportPreviewUrl,
  rerenderClip,
} from "@/lib/api";
import type {
  BrandKit,
  CaptionStyleInfo,
  ManualExport,
  ScoredClipDict,
} from "@/lib/types";
import { fmtDuration, fmtTime } from "@/lib/format";
import Spinner from "@/components/Spinner";
import CaptionStyleSelect from "@/components/CaptionStyleSelect";

const MIN_SECONDS = 5;
const MAX_SECONDS = 90;

export default function ClipEditPage() {
  const params = useParams<{ jobId: string; clipIndex: string }>();
  const jobId = params.jobId;
  const clipIndex = Number(params.clipIndex);

  const [clip, setClip] = useState<ScoredClipDict | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [title, setTitle] = useState("");
  const [captionStyle, setCaptionStyle] = useState("high_energy");
  const [captionMode, setCaptionMode] = useState("karaoke");
  const [removeSilence, setRemoveSilence] = useState(true);
  const [reframeMode, setReframeMode] = useState("smart");

  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [newExport, setNewExport] = useState<ManualExport | null>(null);
  const [exports, setExports] = useState<ManualExport[]>([]);
  const [styles, setStyles] = useState<CaptionStyleInfo[]>([]);
  const [brand, setBrand] = useState<BrandKit | null>(null);

  useEffect(() => {
    getCaptionStyles().then(setStyles).catch(() => {});
    getBrandKit().then(setBrand).catch(() => {});
  }, []);

  // Initial: Clip-Daten laden und Felder vorbefüllen.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await getClips(jobId);
        if (!active) return;
        const c = data.clips[clipIndex - 1] ?? null;
        if (!c) {
          setLoadError("Clip nicht gefunden.");
          return;
        }
        setClip(c);
        setStart(Number(c.start.toFixed(2)));
        setEnd(Number(c.end.toFixed(2)));
        setCaptionStyle(c.caption_info?.caption_style ?? "high_energy");
        setReframeMode(c.reframe_info?.requested_mode ?? "smart");
      } catch (e) {
        if (active)
          setLoadError(
            e instanceof Error ? e.message : "Clip konnte nicht geladen werden.",
          );
      }
    })();
    return () => {
      active = false;
    };
  }, [jobId, clipIndex]);

  const refreshExports = useCallback(async () => {
    try {
      const all = await getManualExports(jobId);
      setExports(all.filter((e) => e.source_clip_index === clipIndex));
    } catch {
      /* Liste ist optional — kein harter Fehler */
    }
  }, [jobId, clipIndex]);

  useEffect(() => {
    refreshExports();
  }, [refreshExports]);

  const duration = useMemo(() => Math.max(0, end - start), [start, end]);
  const durationWarning = useMemo(() => {
    if (end <= start) return "Endzeit muss größer als Startzeit sein.";
    if (duration < MIN_SECONDS)
      return `Zu kurz — mindestens ${MIN_SECONDS}s (aktuell ${duration.toFixed(1)}s).`;
    if (duration > MAX_SECONDS)
      return `Zu lang — höchstens ${MAX_SECONDS}s (aktuell ${duration.toFixed(1)}s).`;
    return null;
  }, [start, end, duration]);

  const canRender = !rendering && !durationWarning;

  async function handleRerender() {
    setRenderError(null);
    setNewExport(null);
    setRendering(true);
    try {
      const result = await rerenderClip(jobId, clipIndex, {
        start_time: start,
        end_time: end,
        title: title.trim() || null,
        caption_style: captionStyle,
        caption_mode: captionMode,
        remove_silence: removeSilence,
        reframe_mode: reframeMode,
      });
      setNewExport(result);
      await refreshExports();
    } catch (e) {
      setRenderError(
        e instanceof Error ? e.message : "Re-Render fehlgeschlagen.",
      );
    } finally {
      setRendering(false);
    }
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link
          href={`/jobs/${jobId}`}
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          ← Zurück zum Job
        </Link>
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {loadError}
        </div>
      </div>
    );
  }

  if (!clip) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <Spinner className="h-4 w-4" /> Lade Clip …
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          href={`/jobs/${jobId}`}
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          ← Zurück zum Job
        </Link>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-white">
          Clip #{clipIndex} bearbeiten
        </h1>
        <p className="mt-1 text-sm text-neutral-400">
          Start/Ende feinjustieren, Optionen wählen und neu exportieren. Der
          ursprüngliche Auto-Clip bleibt unverändert erhalten.
        </p>
      </div>

      {/* Vorschau aktueller Auto-Clip */}
      <div className="overflow-hidden rounded-xl border border-neutral-800 bg-black">
        <video
          controls
          preload="metadata"
          playsInline
          src={clipPreviewUrl(jobId, clipIndex)}
          className="mx-auto max-h-80 w-auto"
        />
      </div>
      <p className="text-xs text-neutral-500">
        Auto-Clip: Start {fmtTime(clip.start)} · Ende {fmtTime(clip.end)} · Länge{" "}
        {fmtDuration(clip.duration)}
      </p>

      {/* Editor-Felder */}
      <div className="space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm text-neutral-300">Startzeit (Sekunden)</span>
            <input
              type="number"
              step={0.1}
              min={0}
              value={start}
              onChange={(e) => setStart(Math.max(0, Number(e.target.value) || 0))}
              className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
            />
          </label>
          <label className="block">
            <span className="text-sm text-neutral-300">Endzeit (Sekunden)</span>
            <input
              type="number"
              step={0.1}
              min={0}
              value={end}
              onChange={(e) => setEnd(Math.max(0, Number(e.target.value) || 0))}
              className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
            />
          </label>
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="text-neutral-400">
            Neue Länge:{" "}
            <span
              className={
                durationWarning ? "text-amber-400" : "text-neutral-100"
              }
            >
              {duration.toFixed(1)}s
            </span>
          </span>
          <span className="text-xs text-neutral-500">
            erlaubt: {MIN_SECONDS}–{MAX_SECONDS}s
          </span>
        </div>
        {durationWarning && (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            ⚠ {durationWarning}
          </p>
        )}

        <label className="block">
          <span className="text-sm text-neutral-300">Titel (optional)</span>
          <input
            type="text"
            value={title}
            placeholder="z. B. Bester Moment"
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          />
        </label>

        {brand?._exists && (
          <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 px-3 py-2 text-xs text-indigo-200">
            🎨 Brand Kit aktiv{brand.brand_name ? `: ${brand.brand_name}` : ""} —
            Marken-Farben/Watermark werden beim Re-Render angewandt.
          </div>
        )}

        {styles.length > 0 && (
          <CaptionStyleSelect
            styles={styles}
            value={captionStyle}
            onChange={setCaptionStyle}
          />
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm text-neutral-300">Untertitel-Modus</span>
            <select
              value={captionMode}
              onChange={(e) => setCaptionMode(e.target.value)}
              className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
            >
              <option value="karaoke">Wortgenau / Karaoke</option>
              <option value="standard">Standard</option>
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
            className="flex items-center justify-between gap-3 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-left"
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

        {renderError && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {renderError}
          </div>
        )}

        <button
          onClick={handleRerender}
          disabled={!canRender}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 font-medium text-neutral-900 transition hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {rendering ? (
            <>
              <Spinner className="h-4 w-4" /> Wird neu gerendert …
            </>
          ) : (
            "Neu rendern"
          )}
        </button>
      </div>

      {/* Ergebnis: neuer Export */}
      {newExport && (
        <div className="space-y-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400">✓</span>
            <h2 className="font-semibold text-neutral-100">
              Manueller Export gespeichert
            </h2>
          </div>
          <p className="font-mono text-xs text-neutral-400">
            Export-ID: <span className="text-neutral-200">{newExport.export_id}</span>
          </p>
          <div className="overflow-hidden rounded-xl border border-neutral-800 bg-black">
            <video
              key={newExport.export_id}
              controls
              preload="metadata"
              playsInline
              src={manualExportPreviewUrl(jobId, newExport.export_id)}
              className="mx-auto max-h-80 w-auto"
            />
          </div>
          <ExportMeta exp={newExport} />
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={manualExportDownloadUrl(jobId, newExport.export_id)}
              download
              className="inline-flex items-center gap-2 rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-neutral-900 transition hover:bg-neutral-200"
            >
              MP4 herunterladen
            </a>
            <Link
              href={`/jobs/${jobId}`}
              className="inline-flex items-center gap-2 rounded-lg border border-neutral-700 px-3.5 py-2 text-sm font-medium text-neutral-200 transition hover:border-neutral-500 hover:text-white"
            >
              Zur Job-Übersicht
            </Link>
          </div>
          <p className="rounded-lg bg-neutral-800/40 px-3 py-2 text-xs text-neutral-400">
            ℹ Dieser Export erscheint jetzt im Bereich{" "}
            <span className="text-neutral-200">„Manuelle Exporte“</span> auf der
            Job-Seite und ist Teil von{" "}
            <span className="text-neutral-200">all-exports.zip</span>.
          </p>
        </div>
      )}

      {/* Bisherige manuelle Exporte für diesen Clip */}
      {exports.length > 0 && (
        <div className="space-y-2 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
          <h2 className="text-sm font-semibold text-neutral-200">
            Manuelle Exporte für Clip #{clipIndex} ({exports.length})
          </h2>
          <ul className="space-y-2">
            {exports.map((e) => (
              <li
                key={e.export_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-neutral-800/40 px-3 py-2 text-xs"
              >
                <span className="text-neutral-300">
                  {e.title || e.export_id}
                  <span className="ml-2 text-neutral-500">
                    {e.start_time.toFixed(1)}–{e.end_time.toFixed(1)}s ·{" "}
                    {e.final_duration.toFixed(1)}s · {e.reframe_mode}
                    {e.remove_silence ? " · Stille-Schnitt" : ""}
                  </span>
                </span>
                <a
                  href={manualExportDownloadUrl(jobId, e.export_id)}
                  download
                  className="rounded-md border border-neutral-700 px-2 py-1 text-neutral-300 transition hover:border-neutral-500 hover:text-white"
                >
                  Download
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ExportMeta({ exp }: { exp: ManualExport }) {
  return (
    <div className="grid gap-x-4 gap-y-1 text-xs text-neutral-400 sm:grid-cols-2">
      <span>
        Bereich:{" "}
        <span className="text-neutral-200">
          {exp.start_time.toFixed(1)}–{exp.end_time.toFixed(1)}s
        </span>
      </span>
      <span>
        Finale Länge:{" "}
        <span className="text-neutral-200">
          {exp.final_duration.toFixed(1)}s
        </span>
      </span>
      <span>
        Caption-Style:{" "}
        <span className="text-neutral-200">{exp.caption_style}</span>
      </span>
      <span>
        Bild: <span className="text-neutral-200">{exp.reframe_mode}</span>
      </span>
      <span>
        Brand Kit:{" "}
        <span className="text-neutral-200">
          {exp.brand_kit_used
            ? exp.brand_kit_name
              ? `an (${exp.brand_kit_name})`
              : "an"
            : "aus"}
        </span>
      </span>
      <span>
        Stille-Schnitt:{" "}
        <span className="text-neutral-200">
          {exp.remove_silence ? "an" : "aus"}
        </span>
      </span>
      {typeof exp.score === "number" && (
        <span>
          Score: <span className="text-neutral-200">{exp.score}</span>
        </span>
      )}
      {exp.warning && (
        <span className="text-amber-400 sm:col-span-2">⚠ {exp.warning}</span>
      )}
    </div>
  );
}
