// Gleiche Keyframe-Kurve wie api/clipforge/studio/timeline.py (value_at) —
// die Live-Vorschau im Browser und der FFmpeg-Render rechnen identisch.
import type { Ease, TimelineItem, TrackKind } from "./studio";

export const DEFAULTS: Record<TrackKind, Record<string, number>> = {
  video: { x: 0.5, y: 0.5, scale: 1, rotation: 0, opacity: 1, volume: 1, crop_left: 0, crop_right: 0, crop_top: 0, crop_bottom: 0, blur: 0 },
  overlay: { x: 0.5, y: 0.5, scale: 0.4, rotation: 0, opacity: 1, volume: 1, crop_left: 0, crop_right: 0, crop_top: 0, crop_bottom: 0, blur: 0 },
  audio: { volume: 1 },
  caption: {},
};

export function ease(name: Ease, p: number): number {
  if (name === "ease_in") return p * p;
  if (name === "ease_out") return 1 - (1 - p) * (1 - p);
  if (name === "ease_in_out") return p < 0.5 ? 2 * p * p : 1 - 2 * (1 - p) * (1 - p);
  return p;
}

/** Statischer Wert eines Elements (ohne Keyframes), inkl. Zuschnitt-Feld. */
function staticValue(item: TimelineItem, prop: string, kind: TrackKind): number {
  if (prop.startsWith("crop_")) {
    const crop = (item as unknown as { crop?: Record<string, number> }).crop;
    return crop?.[prop.slice(5)] ?? 0;
  }
  const v = (item as unknown as Record<string, unknown>)[prop];
  return typeof v === "number" ? v : (DEFAULTS[kind][prop] ?? 0);
}

export function valueAt(item: TimelineItem, prop: string, u: number, kind: TrackKind): number {
  const kfs = item.keyframes?.[prop];
  if (!kfs || kfs.length === 0) return staticValue(item, prop, kind);
  if (u <= kfs[0].t) return kfs[0].v;
  for (let i = 0; i < kfs.length - 1; i += 1) {
    const a = kfs[i];
    const b = kfs[i + 1];
    if (u < b.t) return a.v + (b.v - a.v) * ease(a.ease, (u - a.t) / (b.t - a.t));
  }
  return kfs[kfs.length - 1].v;
}

/** Deckkraft-Faktor aus Ein-/Ausblendung (wie FFmpeg fade=alpha). */
export function fadeFactor(item: TimelineItem, u: number): number {
  let f = 1;
  if (item.fade_in && u < item.fade_in) f *= Math.max(0, u / item.fade_in);
  if (item.fade_out && u > item.duration - item.fade_out) f *= Math.max(0, (item.duration - u) / item.fade_out);
  return f;
}

export function aspectOf(ratio: string): number {
  const [w, h] = ratio.split(":").map(Number);
  return w > 0 && h > 0 ? w / h : 9 / 16;
}
