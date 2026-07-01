"use client";

import type { CaptionStyleInfo } from "@/lib/types";

/**
 * Caption-Style-Auswahl mit Beschreibung + kleiner CSS-Vorschau.
 * Reine CSS-Näherung — die FFmpeg-Ausgabe ist maßgeblich.
 */
export default function CaptionStyleSelect({
  styles,
  value,
  onChange,
  label = "Caption-Style",
}: {
  styles: CaptionStyleInfo[];
  value: string;
  onChange: (v: string) => void;
  label?: string;
}) {
  const current = styles.find((s) => s.style_id === value);

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-sm text-neutral-300">{label}</span>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
        >
          {styles.map((s) => (
            <option key={s.style_id} value={s.style_id}>
              {s.name}
              {s.recommended_for ? ` — ${s.recommended_for}` : ""}
            </option>
          ))}
        </select>
      </label>

      {current && (
        <div className="flex items-center gap-3 rounded-lg border border-neutral-800 bg-neutral-900/50 p-3">
          {/* CSS-Vorschau (nur Annäherung) */}
          <div className="grid h-14 w-24 shrink-0 place-items-center overflow-hidden rounded-md bg-black">
            <span
              className="px-1 text-center text-xs font-extrabold uppercase leading-tight text-white"
              style={{
                WebkitTextStroke: "0.6px #000",
                textShadow: "0 1px 2px rgba(0,0,0,0.8)",
              }}
            >
              {current.preview_label || current.name}
            </span>
          </div>
          <div className="min-w-0">
            <p className="text-xs text-neutral-300">{current.description}</p>
            <p className="mt-0.5 text-[11px] text-neutral-500">
              Vorschau ist nur eine CSS-Näherung — die FFmpeg-Ausgabe ist
              maßgeblich.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
