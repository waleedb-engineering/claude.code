"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Ease, MediaItem, Timeline, TimelineItem, TimelineOp, TimelineTrack, TrackKind } from "@/lib/studio";
import { btnCls, cardCls, inputCls, labelCls } from "./ui";

/**
 * Mehrspur-Timeline: Ziehen (verschieben, auch auf andere Spur), Kanten ziehen (trimmen),
 * Einrasten an Kanten/Abspielkopf, Teilen, Löschen, Ripple-Löschen, Duplizieren, Gruppieren,
 * Slip, Spur stumm/gesperrt/ausgeblendet, Zoom, Abspielkopf, Keyframes mit Easing.
 * Jede Änderung geht als Operation an den Server (dieselbe Funktion wie beim KI-Assistenten);
 * Rückgängig/Wiederholen übernimmt der Editor (Strg+Z / Strg+Y).
 */

const ROW = 44;
const KIND_COLOR: Record<TrackKind, string> = {
  video: "bg-sky-700/80 border-sky-400",
  overlay: "bg-violet-700/80 border-violet-400",
  audio: "bg-emerald-700/80 border-emerald-400",
  caption: "bg-amber-700/80 border-amber-400",
};
const PROPS: Record<TrackKind, string[]> = {
  video: ["x", "y", "scale", "rotation", "opacity", "volume"],
  overlay: ["x", "y", "scale", "rotation", "opacity", "volume"],
  audio: ["volume"],
  caption: [],
};
const KIND_LABEL: Record<TrackKind, string> = { video: "Video", overlay: "Overlay", audio: "Audio", caption: "Text" };

type Drag = {
  id: string;
  mode: "move" | "start" | "end";
  x0: number;
  y0: number;
  start: number;
  duration: number;
  trackIndex: number;
  preview: { start: number; duration: number; trackIndex: number; snap: number | null };
};

function fmt(t: number) {
  const m = Math.floor(t / 60);
  return `${m}:${(t % 60).toFixed(1).padStart(4, "0")}`;
}

export default function TimelineEditor(props: {
  timeline: Timeline;
  media: MediaItem[];
  baseDuration: number | null;
  previewUrl: string | null;
  onOps: (ops: TimelineOp[]) => Promise<boolean>;
}) {
  const { timeline, media, baseDuration, previewUrl, onOps } = props;
  const [zoom, setZoom] = useState(60); // Pixel pro Sekunde
  const [playhead, setPlayhead] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [addKind, setAddKind] = useState<TrackKind>("overlay");
  const [addSrc, setAddSrc] = useState("");
  const [kf, setKf] = useState<{ prop: string; v: string; ease: Ease }>({ prop: "x", v: "0.5", ease: "linear" });
  const [form, setForm] = useState<Record<string, string>>({});
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const areaRef = useRef<HTMLDivElement | null>(null);

  const tracks = timeline.tracks;
  const items = useMemo(() => tracks.flatMap((t) => t.items.map((i) => ({ track: t, item: i }))), [tracks]);
  const end = Math.max(baseDuration ?? 0, ...items.map((x) => x.item.start + x.item.duration), 10);
  const sel = items.find((x) => x.item.id === selected[0]) ?? null;

  const snapPoints = useCallback(
    (exclude: string) => {
      const pts = [0, playhead];
      for (const x of items) if (x.item.id !== exclude) pts.push(x.item.start, x.item.start + x.item.duration);
      if (baseDuration) pts.push(baseDuration);
      return pts;
    },
    [items, playhead, baseDuration],
  );

  function snap(value: number, exclude: string): { v: number; at: number | null } {
    const thr = 8 / zoom;
    let best: number | null = null;
    for (const p of snapPoints(exclude)) if (Math.abs(p - value) <= thr && (best === null || Math.abs(p - value) < Math.abs(best - value))) best = p;
    return best === null ? { v: value, at: null } : { v: best, at: best };
  }

  function onPointerDown(e: React.PointerEvent, track: TimelineTrack, trackIndex: number, item: TimelineItem) {
    e.stopPropagation();
    setSelected((s) => (e.shiftKey ? (s.includes(item.id) ? s.filter((x) => x !== item.id) : [...s, item.id]) : [item.id]));
    if (track.locked) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const local = e.clientX - rect.left;
    const mode = local < 7 ? "start" : local > rect.width - 7 ? "end" : "move";
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDrag({ id: item.id, mode, x0: e.clientX, y0: e.clientY, start: item.start, duration: item.duration, trackIndex,
      preview: { start: item.start, duration: item.duration, trackIndex, snap: null } });
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!drag) return;
    const dt = (e.clientX - drag.x0) / zoom;
    let { start, duration } = drag;
    let trackIndex = drag.trackIndex;
    let at: number | null = null;
    if (drag.mode === "move") {
      const s1 = snap(Math.max(0, drag.start + dt), drag.id);
      const s2 = snap(Math.max(0, drag.start + dt) + drag.duration, drag.id);
      if (s1.at !== null) ({ v: start, at } = s1);
      else if (s2.at !== null) {
        start = s2.v - drag.duration;
        at = s2.at;
      } else start = Math.max(0, drag.start + dt);
      const ti = drag.trackIndex + Math.round((e.clientY - drag.y0) / ROW);
      if (ti >= 0 && ti < tracks.length && compatible(tracks[drag.trackIndex].kind, tracks[ti].kind) && !tracks[ti].locked) trackIndex = ti;
    } else if (drag.mode === "start") {
      const s = snap(Math.min(drag.start + drag.duration - 0.05, Math.max(0, drag.start + dt)), drag.id);
      start = s.v;
      at = s.at;
      duration = drag.start + drag.duration - start;
    } else {
      const s = snap(Math.max(drag.start + 0.05, drag.start + drag.duration + dt), drag.id);
      duration = s.v - drag.start;
      at = s.at;
    }
    setDrag({ ...drag, preview: { start, duration, trackIndex, snap: at } });
  }

  async function onPointerUp() {
    if (!drag) return;
    const d = drag;
    setDrag(null);
    const p = d.preview;
    if (Math.abs(p.start - d.start) < 1e-3 && Math.abs(p.duration - d.duration) < 1e-3 && p.trackIndex === d.trackIndex) return;
    if (d.mode === "move") {
      const op: TimelineOp = { op: "move", item: d.id, start: round(p.start), snap: false };
      if (p.trackIndex !== d.trackIndex) op.track = tracks[p.trackIndex].id;
      await onOps([op]);
    } else if (d.mode === "start") await onOps([{ op: "trim", item: d.id, edge: "start", time: round(p.start), snap: false }]);
    else await onOps([{ op: "trim", item: d.id, edge: "end", time: round(p.start + p.duration), snap: false }]);
  }

  const act = useCallback(
    async (op: string) => {
      if (!selected.length) return;
      const id = selected[0];
      if (op === "split") await onOps([{ op: "split", item: id, at: round(playhead) }]);
      else if (op === "group") await onOps([{ op: "group", items: selected }]);
      else await onOps([{ op, item: id }]);
      if (op === "delete" || op === "ripple_delete") setSelected([]);
    },
    [selected, playhead, onOps],
  );

  // Tastenkürzel (außerhalb von Eingabefeldern)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (!areaRef.current?.contains(document.activeElement) && document.activeElement !== document.body) return;
      if (e.key === "s" && !e.ctrlKey && !e.metaKey) void act("split");
      else if (e.key === "Delete" || e.key === "Backspace") void act(e.shiftKey ? "ripple_delete" : "delete");
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
        e.preventDefault();
        void act("duplicate");
      } else if (e.key === "ArrowLeft") setPlayhead((p) => Math.max(0, p - (e.shiftKey ? 1 : 0.1)));
      else if (e.key === "ArrowRight") setPlayhead((p) => p + (e.shiftKey ? 1 : 0.1));
      else if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(400, z * 1.25));
      else if (e.key === "-") setZoom((z) => Math.max(8, z / 1.25));
      else return;
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act]);

  useEffect(() => {
    const v = videoRef.current;
    if (v && v.paused && Math.abs(v.currentTime - playhead) > 0.05) v.currentTime = Math.min(playhead, v.duration || playhead);
  }, [playhead]);

  async function addItem() {
    const item: Record<string, unknown> = { start: round(playhead), duration: 3 };
    if (addKind === "caption") item.text = addSrc || "Text";
    else {
      if (!addSrc) return;
      item.src = addSrc;
    }
    await onOps([{ op: "add_item", track_kind: addKind, item }]);
  }

  const visibleMedia = media.filter((m) => (addKind === "audio" ? m.kind === "audio" || m.kind === "video" : m.kind !== "audio"));
  const ticks = Array.from({ length: Math.ceil(end) + 1 }, (_, i) => i).filter((i) => i % (zoom < 20 ? 10 : zoom < 50 ? 5 : 1) === 0);

  return (
    <section className={`${cardCls} space-y-3`} aria-label="Mehrspur-Timeline" ref={areaRef} tabIndex={-1}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-neutral-200">Mehrspur-Timeline</h2>
        <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
          <span data-testid="tl-playhead">▼ {fmt(playhead)}</span>
          <label className="flex items-center gap-1">
            Zoom
            <input type="range" min={8} max={400} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} aria-label="Timeline-Zoom" />
          </label>
        </div>
      </div>

      {previewUrl && (
        <video
          ref={videoRef}
          src={previewUrl}
          controls
          className="max-h-56 rounded-lg"
          onTimeUpdate={(e) => {
            if (!e.currentTarget.paused) setPlayhead(e.currentTarget.currentTime);
          }}
        />
      )}
      {!previewUrl && <p className="text-xs text-neutral-500">Vorschau: nach „Vorschau rendern“ hier abspielbar (Abspielkopf synchron).</p>}

      <div className="flex flex-wrap gap-2">
        {(["split", "duplicate", "delete", "ripple_delete", "group", "ungroup"] as const).map((op) => (
          <button key={op} type="button" className={btnCls} disabled={!selected.length || (op === "group" && selected.length < 2)} onClick={() => void act(op)}>
            {{ split: "✂ Teilen (S)", duplicate: "⧉ Duplizieren (Strg+D)", delete: "🗑 Löschen (Entf)", ripple_delete: "⇤ Ripple-Löschen (⇧Entf)", group: "Gruppieren", ungroup: "Gruppe lösen" }[op]}
          </button>
        ))}
        {(["video", "overlay", "audio", "caption"] as TrackKind[]).map((k) => (
          <button key={k} type="button" className={btnCls} onClick={() => void onOps([{ op: "add_track", kind: k }])}>
            + {KIND_LABEL[k]}-Spur
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-lg border border-neutral-800" onPointerMove={onPointerMove} onPointerUp={() => void onPointerUp()}>
        <div style={{ width: 140 + end * zoom + 40 }} className="relative select-none">
          {/* Lineal */}
          <div
            className="relative ml-[140px] h-6 cursor-pointer border-b border-neutral-800 text-[10px] text-neutral-500"
            onPointerDown={(e) => setPlayhead(Math.max(0, (e.clientX - e.currentTarget.getBoundingClientRect().left) / zoom))}
            role="slider"
            aria-label="Abspielkopf"
            aria-valuenow={Math.round(playhead * 10) / 10}
            aria-valuemin={0}
            aria-valuemax={Math.round(end)}
            tabIndex={0}
          >
            {ticks.map((i) => (
              <span key={i} className="absolute top-0 border-l border-neutral-700 pl-0.5" style={{ left: i * zoom }}>
                {fmt(i)}
              </span>
            ))}
          </div>
          {baseDuration ? (
            <div className="flex h-7 items-center border-b border-neutral-800">
              <div className="w-[140px] shrink-0 px-2 text-xs text-neutral-400">Szenen-Programm</div>
              <div className="h-5 rounded bg-neutral-700/70 text-[10px] leading-5 text-neutral-300" style={{ width: baseDuration * zoom }}>
                &nbsp;Grundebene ({fmt(baseDuration)})
              </div>
            </div>
          ) : null}
          {tracks.map((track, ti) => (
            <div key={track.id} className="flex border-b border-neutral-800" style={{ height: ROW }} data-testid={`tl-track-${track.kind}`}>
              <div className="flex w-[140px] shrink-0 items-center gap-1 px-2 text-xs text-neutral-300">
                <span className="truncate" title={track.name}>
                  {track.name}
                </span>
                {(["muted", "locked", "hidden"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    aria-pressed={track[f]}
                    title={{ muted: "Stumm", locked: "Sperren", hidden: "Ausblenden" }[f]}
                    aria-label={`${{ muted: "Stumm", locked: "Sperren", hidden: "Ausblenden" }[f]}: ${track.name}`}
                    className={`rounded px-1 ${track[f] ? "bg-indigo-600 text-white" : "text-neutral-500 hover:text-white"}`}
                    onClick={() => void onOps([{ op: "set_track", track: track.id, [f]: !track[f] }])}
                  >
                    {{ muted: "M", locked: "L", hidden: "H" }[f]}
                  </button>
                ))}
              </div>
              <div className={`relative flex-1 ${track.hidden ? "opacity-40" : ""}`}>
                {track.items.map((item) => {
                  const live = drag?.id === item.id ? drag.preview : null;
                  if (live && live.trackIndex !== ti) return null;
                  const start = live ? live.start : item.start;
                  const dur = live ? live.duration : item.duration;
                  const kfCount = Object.values(item.keyframes ?? {}).reduce((a, k) => a + k.length, 0);
                  return (
                    <div
                      key={item.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`${KIND_LABEL[track.kind]} ${item.text ?? item.src ?? ""} ${fmt(item.start)}`}
                      data-testid="tl-item"
                      onPointerDown={(e) => onPointerDown(e, track, ti, item)}
                      onKeyDown={(e) => e.key === "Enter" && setSelected([item.id])}
                      className={`absolute top-1 bottom-1 cursor-grab overflow-hidden rounded border px-1 text-[11px] text-white ${KIND_COLOR[track.kind]} ${
                        selected.includes(item.id) ? "ring-2 ring-white" : ""
                      } ${track.locked ? "cursor-not-allowed opacity-70" : ""}`}
                      style={{ left: start * zoom, width: Math.max(6, dur * zoom) }}
                    >
                      {item.group ? "⛓ " : ""}
                      {item.text ?? item.src}
                      {kfCount ? ` ◆${kfCount}` : ""}
                    </div>
                  );
                })}
                {drag && drag.preview.trackIndex === ti && drag.preview.trackIndex !== drag.trackIndex && (
                  <div className="absolute top-1 bottom-1 rounded border border-dashed border-white/70" style={{ left: drag.preview.start * zoom, width: drag.preview.duration * zoom }} />
                )}
              </div>
            </div>
          ))}
          {tracks.length === 0 && <p className="ml-[140px] p-3 text-xs text-neutral-500">Noch keine Spuren — oben eine Spur anlegen.</p>}
          {/* Abspielkopf + Einrastlinie */}
          <div className="pointer-events-none absolute top-0 bottom-0 w-px bg-red-500" style={{ left: 140 + playhead * zoom }} />
          {drag?.preview.snap != null && <div className="pointer-events-none absolute top-0 bottom-0 w-px bg-yellow-300" style={{ left: 140 + drag.preview.snap * zoom }} />}
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <div>
          <label className={labelCls} htmlFor="tl-kind">
            Hinzufügen auf
          </label>
          <select id="tl-kind" className={inputCls} value={addKind} onChange={(e) => setAddKind(e.target.value as TrackKind)}>
            {(["overlay", "video", "audio", "caption"] as TrackKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className={labelCls} htmlFor="tl-src">
            {addKind === "caption" ? "Text" : "Medium aus dem Projekt"}
          </label>
          {addKind === "caption" ? (
            <input id="tl-src" className={inputCls} value={addSrc} onChange={(e) => setAddSrc(e.target.value)} />
          ) : (
            <select id="tl-src" className={inputCls} value={addSrc} onChange={(e) => setAddSrc(e.target.value)}>
              <option value="">– wählen –</option>
              {visibleMedia.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-end">
          <button type="button" className={btnCls} onClick={() => void addItem()}>
            + am Abspielkopf
          </button>
        </div>
      </div>

      {sel && (
        <div className="space-y-2 rounded-lg border border-neutral-800 p-3" aria-label="Eigenschaften">
          <p className="text-xs text-neutral-400">
            {KIND_LABEL[sel.track.kind]} · {sel.item.text ?? sel.item.src} · {fmt(sel.item.start)} – {fmt(sel.item.start + sel.item.duration)}
            {sel.track.locked ? " · Spur gesperrt" : ""}
          </p>
          <div className="grid gap-2 sm:grid-cols-4">
            {fieldsFor(sel.track.kind).map((f) => (
              <div key={f}>
                <label className={labelCls} htmlFor={`tl-f-${f}`}>
                  {f}
                </label>
                <input
                  id={`tl-f-${f}`}
                  className={inputCls}
                  value={form[`${sel.item.id}:${f}`] ?? String((sel.item as Record<string, unknown>)[f] ?? "")}
                  onChange={(e) => setForm({ ...form, [`${sel.item.id}:${f}`]: e.target.value })}
                />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={btnCls}
              onClick={async () => {
                const props: Record<string, unknown> = {};
                for (const f of fieldsFor(sel.track.kind)) {
                  const v = form[`${sel.item.id}:${f}`];
                  if (v === undefined) continue;
                  props[f] = ["text", "color", "position", "src"].includes(f) ? v : Number(v);
                }
                if (await onOps([{ op: "set_item", item: sel.item.id, props }])) setForm({});
              }}
            >
              Eigenschaften übernehmen
            </button>
            {sel.item.in !== undefined && (
              <>
                <button type="button" className={btnCls} onClick={() => void onOps([{ op: "slip", item: sel.item.id, delta: -0.5 }])}>
                  ◀ Slip −0,5 s
                </button>
                <button type="button" className={btnCls} onClick={() => void onOps([{ op: "slip", item: sel.item.id, delta: 0.5 }])}>
                  Slip +0,5 s ▶
                </button>
              </>
            )}
          </div>
          {PROPS[sel.track.kind].length > 0 && (
            <div className="space-y-1 border-t border-neutral-800 pt-2">
              <p className="text-xs text-neutral-400">Keyframe am Abspielkopf (lokal {Math.max(0, playhead - sel.item.start).toFixed(2)} s)</p>
              <div className="flex flex-wrap items-end gap-2">
                <select aria-label="Keyframe-Eigenschaft" className={inputCls} value={kf.prop} onChange={(e) => setKf({ ...kf, prop: e.target.value })}>
                  {PROPS[sel.track.kind].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
                <input aria-label="Keyframe-Wert" className={`${inputCls} w-24`} value={kf.v} onChange={(e) => setKf({ ...kf, v: e.target.value })} />
                <select aria-label="Keyframe-Übergang" className={inputCls} value={kf.ease} onChange={(e) => setKf({ ...kf, ease: e.target.value as Ease })}>
                  {(["linear", "ease_in", "ease_out", "ease_in_out"] as Ease[]).map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className={btnCls}
                  disabled={playhead < sel.item.start || playhead > sel.item.start + sel.item.duration}
                  onClick={() =>
                    void onOps([{ op: "set_keyframe", item: sel.item.id, prop: kf.prop, t: round(playhead - sel.item.start), v: Number(kf.v), ease: kf.ease }])
                  }
                >
                  ◆ Keyframe setzen
                </button>
              </div>
              <ul className="text-xs text-neutral-300">
                {Object.entries(sel.item.keyframes ?? {}).flatMap(([prop, list]) =>
                  list.map((k) => (
                    <li key={`${prop}-${k.t}`}>
                      ◆ {prop} @ {k.t.toFixed(2)} s = {k.v} ({k.ease}){" "}
                      <button type="button" className="underline" onClick={() => void onOps([{ op: "remove_keyframe", item: sel.item.id, prop, t: k.t }])}>
                        entfernen
                      </button>
                    </li>
                  )),
                )}
              </ul>
            </div>
          )}
        </div>
      )}
      <p className="text-[11px] text-neutral-500">
        Ziehen = verschieben (auch auf andere Spur), Kanten = trimmen, ⇧+Klick = Mehrfachauswahl, ←/→ Abspielkopf, +/− Zoom. Änderungen wirken beim Rendern.
      </p>
    </section>
  );
}

function compatible(a: TrackKind, b: TrackKind) {
  return a === b || (a !== "audio" && a !== "caption" && b !== "audio" && b !== "caption");
}

function round(v: number) {
  return Math.round(v * 1000) / 1000;
}

function fieldsFor(kind: TrackKind): string[] {
  if (kind === "caption") return ["start", "duration", "text", "color", "position", "size"];
  if (kind === "audio") return ["start", "duration", "in", "volume", "fade_in", "fade_out"];
  return ["start", "duration", "in", "x", "y", "scale", "rotation", "opacity", "blur", "volume", "fade_in", "fade_out"];
}
