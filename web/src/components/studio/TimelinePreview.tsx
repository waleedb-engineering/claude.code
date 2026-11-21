"use client";

import { useEffect, useRef, useState } from "react";
import type { Timeline, TimelineItem, TrackKind } from "@/lib/studio";
import { aspectOf, fadeFactor, valueAt } from "@/lib/timeline";

/**
 * Live-Vorschau der Mehrspur-Timeline im Browser.
 * Grundebene: Szenenprogramm ohne Timeline-Spuren (aus dem letzten Vorschau-Render) oder schwarz.
 * Darüber: Bild-/Videoelemente mit denselben Keyframe-Kurven wie der Render, Text-Elemente.
 * Die gerenderte FFmpeg-Ausgabe bleibt die Referenz; Abweichungen werden angezeigt.
 */
export default function TimelinePreview(props: {
  timeline: Timeline;
  aspectRatio: string;
  playhead: number;
  setPlayhead: (t: number) => void;
  end: number;
  baseUrl: string | null;
  mediaUrl: (name: string) => string;
  isVideo: (name: string) => boolean;
}) {
  const { timeline, aspectRatio, playhead, setPlayhead, end, baseUrl, mediaUrl, isVideo } = props;
  const [playing, setPlaying] = useState(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const baseRef = useRef<HTMLVideoElement | null>(null);
  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({});
  const [stageW, setStageW] = useState(270);
  const raf = useRef<number | null>(null);
  const clock = useRef<{ t0: number; p0: number } | null>(null);

  // Bühnenbreite messen (für Pixelgrößen von Text/Unschärfe)
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setStageW(el.clientWidth || 270));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Wiedergabe-Uhr
  useEffect(() => {
    if (!playing) return;
    clock.current = { t0: performance.now(), p0: playhead };
    const tick = () => {
      const c = clock.current!;
      const t = c.p0 + (performance.now() - c.t0) / 1000;
      if (t >= end) {
        setPlayhead(end);
        setPlaying(false);
        return;
      }
      setPlayhead(t);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Start nur beim Umschalten
  }, [playing]);

  // Videos auf den Abspielkopf synchronisieren
  useEffect(() => {
    const syncOne = (v: HTMLVideoElement | null, target: number) => {
      if (!v || Number.isNaN(target)) return;
      if (Math.abs(v.currentTime - target) > (playing ? 0.25 : 0.04)) v.currentTime = Math.max(0, target);
      if (playing && v.paused) void v.play().catch(() => undefined);
      if (!playing && !v.paused) v.pause();
    };
    syncOne(baseRef.current, playhead);
    for (const t of timeline.tracks) {
      for (const it of t.items) {
        const v = videoRefs.current[it.id];
        if (v) syncOne(v, (it.in ?? 0) + (playhead - it.start));
      }
    }
  }, [playhead, playing, timeline]);

  const ar = aspectOf(aspectRatio);
  const unsupported: string[] = [];
  const layers: React.ReactNode[] = [];
  timeline.tracks.forEach((track, ti) => {
    if (track.hidden) return;
    for (const it of track.items) {
      const u = playhead - it.start;
      const visible = u >= 0 && u < it.duration;
      if (track.kind === "caption") {
        if (visible && it.text) layers.push(caption(it, stageW, `${track.id}-${it.id}`, ti));
        continue;
      }
      if (track.kind === "audio" || !it.src) continue;
      if (Object.keys(it.keyframes ?? {}).some((p) => p === "blur") || (it.blur ?? 0) > 0) unsupported.push("Unschärfe (Vorschau angenähert)");
      layers.push(visual(it, track.kind, u, visible, stageW, ti));
    }
  });

  function visual(it: TimelineItem, kind: TrackKind, u: number, visible: boolean, w: number, z: number) {
    const v = (p: string) => valueAt(it, p, Math.max(0, Math.min(it.duration, u)), kind);
    const crop = { l: v("crop_left"), r: v("crop_right"), t: v("crop_top"), b: v("crop_bottom") };
    const style: React.CSSProperties = {
      position: "absolute",
      left: `${v("x") * 100}%`,
      top: `${v("y") * 100}%`,
      width: `${v("scale") * 100}%`,
      transform: `translate(-50%, -50%) rotate(${v("rotation")}deg)`,
      opacity: visible ? Math.max(0, Math.min(1, v("opacity") * fadeFactor(it, u))) : 0,
      clipPath: crop.l || crop.r || crop.t || crop.b ? `inset(${crop.t * 100}% ${crop.r * 100}% ${crop.b * 100}% ${crop.l * 100}%)` : undefined,
      filter: v("blur") > 0 ? `blur(${(v("blur") * w) / 1080}px)` : undefined,
      zIndex: 10 + z,
      pointerEvents: "none",
    };
    const label = `Vorschau ${it.src}`;
    if (isVideo(it.src!)) {
      return (
        <video
          key={it.id}
          ref={(el) => {
            videoRefs.current[it.id] = el;
          }}
          src={mediaUrl(it.src!)}
          muted
          playsInline
          preload="auto"
          style={style}
          aria-label={label}
          data-testid="tl-preview-layer"
        />
      );
    }
    // eslint-disable-next-line @next/next/no-img-element
    return <img key={it.id} src={mediaUrl(it.src!)} alt={label} style={style} data-testid="tl-preview-layer" />;
  }

  return (
    <div className="space-y-2">
      <div
        ref={stageRef}
        className="relative mx-auto w-full max-w-[270px] overflow-hidden rounded-lg bg-black"
        style={{ aspectRatio: `${ar}` }}
        aria-label="Live-Vorschau"
        data-testid="tl-preview"
      >
        {baseUrl && <video ref={baseRef} src={baseUrl} muted playsInline preload="auto" className="absolute inset-0 h-full w-full object-contain" />}
        {layers}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-neutral-400">
        <button type="button" className="rounded border border-neutral-700 px-2 py-1 text-neutral-200" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause" : "Abspielen"}>
          {playing ? "⏸" : "▶"}
        </button>
        <button type="button" className="rounded border border-neutral-700 px-2 py-1" onClick={() => setPlayhead(Math.max(0, playhead - 1 / 30))} aria-label="Ein Bild zurück">
          ◀|
        </button>
        <button type="button" className="rounded border border-neutral-700 px-2 py-1" onClick={() => setPlayhead(playhead + 1 / 30)} aria-label="Ein Bild vor">
          |▶
        </button>
        <span>Live-Vorschau ohne Ton · {baseUrl ? "Grundebene aus letztem Vorschau-Render" : "ohne Grundebene"}</span>
      </div>
      {unsupported.length > 0 && (
        <p className="text-center text-xs text-amber-300">Nicht exakt darstellbar: {[...new Set(unsupported)].join(", ")} — maßgeblich ist „Vorschau rendern“.</p>
      )}
    </div>
  );
}

function caption(it: TimelineItem, w: number, key: string, z: number) {
  const pos = it.position ?? "bottom";
  const fs = Math.max(8, w * 0.06 * (it.size ?? 1) * 0.96);
  const style: React.CSSProperties = {
    position: "absolute",
    left: "6%",
    right: "6%",
    textAlign: "center",
    color: it.color ?? "#ffffff",
    fontWeight: 700,
    fontSize: fs,
    lineHeight: 1.15,
    textShadow: "0 0 3px #000, 0 0 3px #000",
    zIndex: 100 + z,
    ...(pos === "top" ? { top: "12%" } : pos === "middle" ? { top: "50%", transform: "translateY(-50%)" } : { bottom: "12%" }),
  };
  return (
    <div key={key} style={style} data-testid="tl-preview-caption">
      {it.text}
    </div>
  );
}
