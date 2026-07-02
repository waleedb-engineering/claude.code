"use client";

import { useState } from "react";
import type { ScoredClipDict } from "@/lib/types";

const HOOK_LABELS: Record<string, string> = {
  question: "Frage-Hook",
  number: "Zahlen-Hook",
  bold_claim: "These/Claim",
  story: "Story-Hook",
  statement: "Aussage",
};
const MODE_LABELS: Record<string, string> = {
  rule_based: "Regelbasiert",
  llm: "KI (Claude)",
  fallback: "Fallback",
};

const COMPONENT_LABELS: { key: string; label: string }[] = [
  { key: "hook_strength", label: "Hook" },
  { key: "retention_potential", label: "Retention" },
  { key: "context_independence", label: "Kontext-frei" },
  { key: "clarity", label: "Klarheit" },
  { key: "emotional_intensity", label: "Emotion" },
  { key: "information_density", label: "Dichte" },
  { key: "share_comment_potential", label: "Teilen" },
  { key: "platform_fit", label: "Platform-Fit" },
  { key: "uniqueness", label: "Einzigartig" },
  { key: "editability", label: "Schneidbar" },
];

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md bg-neutral-800 px-1.5 py-0.5 text-[11px] text-neutral-300">
      {children}
    </span>
  );
}

/** Kompakte v2-Analyse. Rendert nur, wenn v2-Felder vorhanden sind. */
export default function AnalysisV2Panel({ clip }: { clip: ScoredClipDict }) {
  const [open, setOpen] = useState(false);
  if (clip.analyzer_version !== "v2") return null;

  const bd = clip.score_breakdown ?? {};
  const suggestions = clip.improvement_suggestions ?? [];
  const flags = clip.risk_flags ?? [];

  return (
    <div className="space-y-2 rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {clip.hook_type && <Chip>{HOOK_LABELS[clip.hook_type] ?? clip.hook_type}</Chip>}
        {clip.clip_type && <Chip>{clip.clip_type}</Chip>}
        {clip.best_platform && (
          <span className="rounded-md bg-indigo-500/15 px-1.5 py-0.5 text-[11px] text-indigo-300">
            📱 {clip.best_platform}
          </span>
        )}
        {clip.analyzer_mode && (
          <span className="rounded-md border border-neutral-700 px-1.5 py-0.5 text-[11px] text-neutral-400">
            {MODE_LABELS[clip.analyzer_mode] ?? clip.analyzer_mode}
          </span>
        )}
      </div>

      {flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {flags.map((f) => (
            <span
              key={f}
              className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300"
            >
              ⚠ {f}
            </span>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] text-neutral-400 hover:text-neutral-200"
      >
        {open ? "▲ Score-Details ausblenden" : "▼ Score-Details & Tipps"}
      </button>

      {open && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {COMPONENT_LABELS.map(({ key, label }) => (
              <div key={key} className="flex items-center gap-2">
                <span className="w-20 shrink-0 text-[10px] text-neutral-500">
                  {label}
                </span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-neutral-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500"
                    style={{ width: `${Math.max(0, Math.min(100, bd[key] ?? 0))}%` }}
                  />
                </div>
                <span className="w-6 shrink-0 text-right text-[10px] tabular-nums text-neutral-500">
                  {Math.round(bd[key] ?? 0)}
                </span>
              </div>
            ))}
          </div>

          {clip.platform_reason && (
            <p className="text-[11px] text-neutral-500">{clip.platform_reason}</p>
          )}

          {suggestions.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">
                Verbesserungsvorschläge
              </p>
              <ul className="space-y-0.5">
                {suggestions.map((s, i) => (
                  <li key={i} className="text-[11px] text-neutral-400">
                    · {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
