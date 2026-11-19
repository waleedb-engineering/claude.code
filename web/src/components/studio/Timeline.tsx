"use client";

import type { Scene } from "@/lib/studio";

type Props = {
  scenes: Scene[];
  onSelect: (index: number) => void;
  onMove: (from: number, to: number) => void;
};

const COLORS: Record<string, string> = {
  motion: "bg-indigo-500/60",
  static: "bg-slate-500/60",
  media: "bg-emerald-500/60",
  ai_image: "bg-fuchsia-500/60",
  ai_video: "bg-pink-500/60",
  avatar: "bg-amber-500/60",
  split: "bg-cyan-500/60",
};

/** Timeline: Szenen als Blöcke (Breite ≈ Dauer), Spuren für Stimme/Untertitel/Übergänge.
 *  Klick wählt eine Szene, Ziehen ordnet um — gleiche Änderungen wie in der Liste. */
export default function Timeline({ scenes, onSelect, onMove }: Props) {
  const durs = scenes.map((s) => s.duration ?? (s.audio_source ? s.audio_source.end - s.audio_source.start : Math.max(1.5, s.text.split(/\s+/).length / 2.6)));
  const total = durs.reduce((a, b) => a + b, 0) || 1;
  const starts = durs.map((_, i) => durs.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <div className="space-y-1 rounded-xl border border-neutral-800 bg-neutral-950 p-2" aria-label="Timeline">
      <div className="flex justify-between text-[10px] text-neutral-500">
        <span>0 s</span>
        <span>≈ {total.toFixed(0)} s</span>
      </div>
      <div className="flex h-10 w-full gap-px" role="list" aria-label="Video">
        {scenes.map((s, i) => (
          <button
            key={s.id}
            type="button"
            role="listitem"
            draggable
            title={`${i + 1}: ${s.text.slice(0, 60)}`}
            onClick={() => onSelect(i)}
            onDragStart={(e) => e.dataTransfer.setData("text/clipforge-timeline", String(i))}
            onDragOver={(e) => e.dataTransfer.types.includes("text/clipforge-timeline") && e.preventDefault()}
            onDrop={(e) => {
              const from = Number(e.dataTransfer.getData("text/clipforge-timeline"));
              if (Number.isInteger(from) && from !== i) onMove(from, i);
            }}
            className={`${COLORS[s.visual.mode] ?? "bg-neutral-600"} relative min-w-[18px] overflow-hidden rounded text-[10px] text-white hover:ring-2 hover:ring-white/60`}
            style={{ width: `${(durs[i] / total) * 100}%` }}
          >
            {i > 0 && s.transition && s.transition !== "cut" && <span className="absolute left-0 top-0 h-full w-1 bg-white/50" aria-hidden />}
            <span className="px-1">{i + 1}</span>
          </button>
        ))}
      </div>
      <div className="flex h-3 w-full gap-px" aria-label="Stimme">
        {scenes.map((s, i) => (
          <div
            key={s.id}
            className={`${s.audio_source || s.voice_media ? "bg-sky-400/60" : s.text ? "bg-sky-700/60" : "bg-transparent"} rounded`}
            style={{ width: `${(durs[i] / total) * 100}%` }}
            title={`${starts[i].toFixed(1)} s`}
          />
        ))}
      </div>
      <div className="flex h-2 w-full gap-px" aria-label="Untertitel">
        {scenes.map((s, i) => (
          <div key={s.id} className={`${s.text ? "bg-yellow-400/50" : "bg-transparent"} rounded`} style={{ width: `${(durs[i] / total) * 100}%` }} />
        ))}
      </div>
      <p className="text-[10px] text-neutral-500">Video · Stimme · Untertitel — Klick wählt, Ziehen ordnet um. Tasten: Strg+Z/Y, Strg+S.</p>
    </div>
  );
}
