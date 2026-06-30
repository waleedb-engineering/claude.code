// Kleine Anzeige-Helfer (rein UI, keine Geschäftslogik).

export function fmtTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function fmtDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${s}s`;
}

export interface ScoreTier {
  label: string;
  text: string; // Tailwind-Textfarbe
  ring: string; // Hex für SVG-Ring
  bg: string; // Badge-Hintergrund
  border: string;
}

export function scoreTier(score: number): ScoreTier {
  if (score >= 75)
    return {
      label: "Stark",
      text: "text-emerald-400",
      ring: "#34d399",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/30",
    };
  if (score >= 55)
    return {
      label: "Solide",
      text: "text-amber-400",
      ring: "#fbbf24",
      bg: "bg-amber-500/10",
      border: "border-amber-500/30",
    };
  return {
    label: "Schwach",
    text: "text-rose-400",
    ring: "#fb7185",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
  };
}

export function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Liefert einen brauchbaren Titel: erste LLM-Metadaten-Überschrift,
// sonst Fallback "Clip N".
export function clipTitle(
  metadata: Record<string, { title: string }>,
  index: number,
): string {
  for (const key of ["tiktok", "reels", "shorts"]) {
    const t = metadata?.[key]?.title?.trim();
    if (t) return t;
  }
  const any = Object.values(metadata || {}).find((m) => m?.title?.trim());
  if (any) return any.title;
  return `Clip ${index}`;
}
