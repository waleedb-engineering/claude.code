"use client";

import { useState } from "react";
import Link from "next/link";
import type { ManualExport } from "@/lib/types";
import {
  manualExportDownloadUrl,
  manualExportPreviewUrl,
} from "@/lib/api";

function ExportRow({
  jobId,
  exp,
}: {
  jobId: string;
  exp: ManualExport;
}) {
  const [showPreview, setShowPreview] = useState(false);
  return (
    <li className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-neutral-800 px-1.5 py-0.5 text-[11px] font-medium text-neutral-400">
              Clip #{exp.source_clip_index}
            </span>
            <h4 className="truncate font-medium text-neutral-100">
              {exp.title || exp.export_id}
            </h4>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-400">
            <span>
              {exp.start_time.toFixed(1)}–{exp.end_time.toFixed(1)}s
            </span>
            <span className="text-neutral-600">·</span>
            <span>Länge {exp.final_duration.toFixed(1)}s</span>
            <span className="text-neutral-600">·</span>
            <span>{exp.caption_style}</span>
            <span className="text-neutral-600">·</span>
            <span>Bild: {exp.reframe_mode}</span>
            <span className="text-neutral-600">·</span>
            <span>Stille-Schnitt: {exp.remove_silence ? "an" : "aus"}</span>
          </div>
        </div>
      </div>

      {showPreview && (
        <div className="mt-3 overflow-hidden rounded-lg border border-neutral-800 bg-black">
          <video
            controls
            preload="metadata"
            playsInline
            src={manualExportPreviewUrl(jobId, exp.export_id)}
            className="mx-auto max-h-72 w-auto"
          />
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setShowPreview((v) => !v)}
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 transition hover:border-neutral-500 hover:text-white"
        >
          {showPreview ? "Vorschau ausblenden" : "Vorschau"}
        </button>
        <a
          href={manualExportDownloadUrl(jobId, exp.export_id)}
          download
          className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-neutral-900 transition hover:bg-neutral-200"
        >
          Download
        </a>
        <Link
          href={`/jobs/${jobId}/clips/${exp.source_clip_index}/edit`}
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-300 transition hover:border-neutral-500 hover:text-white"
        >
          Zum Editor
        </Link>
        {exp.warning && (
          <span className="text-xs text-amber-400">⚠ {exp.warning}</span>
        )}
      </div>
    </li>
  );
}

export default function ManualExportsSection({
  jobId,
  exports,
}: {
  jobId: string;
  exports: ManualExport[];
}) {
  if (!exports.length) return null;
  // Neueste zuerst (Backend liefert bereits so, aber defensiv sortieren).
  const sorted = [...exports].sort((a, b) =>
    (b.created_at || "").localeCompare(a.created_at || ""),
  );
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Manuelle Exporte</h2>
        <span className="text-xs text-neutral-500">
          {exports.length} gesamt · aus dem Clip-Editor
        </span>
      </div>
      <ul className="space-y-3">
        {sorted.map((e) => (
          <ExportRow key={e.export_id} jobId={jobId} exp={e} />
        ))}
      </ul>
    </section>
  );
}
