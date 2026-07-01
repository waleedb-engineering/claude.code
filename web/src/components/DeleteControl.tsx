"use client";

import { useState } from "react";

/**
 * Kleiner Aktions-Button mit Inline-Bestätigung (kein natives confirm()).
 * `tone="danger"` (rot, löschen) oder `tone="warning"` (amber, z. B. abbrechen).
 */
export default function DeleteControl({
  onConfirm,
  label = "Löschen",
  confirmLabel = "Wirklich löschen?",
  confirmActionLabel = "Ja, löschen",
  busyLabel = "Lösche …",
  errorFallback = "Löschen fehlgeschlagen.",
  tone = "danger",
  disabled = false,
  disabledHint,
  size = "sm",
  onDone,
}: {
  onConfirm: () => Promise<void>;
  label?: string;
  confirmLabel?: string;
  confirmActionLabel?: string;
  busyLabel?: string;
  errorFallback?: string;
  tone?: "danger" | "warning";
  disabled?: boolean;
  disabledHint?: string;
  size?: "sm" | "md";
  onDone?: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pad = size === "md" ? "px-3 py-2" : "px-2.5 py-1.5";
  const text = size === "md" ? "text-sm" : "text-xs";
  const outline =
    tone === "danger"
      ? "border-rose-500/30 text-rose-300 hover:border-rose-500/60 hover:bg-rose-500/10"
      : "border-amber-500/30 text-amber-300 hover:border-amber-500/60 hover:bg-amber-500/10";
  const solid =
    tone === "danger"
      ? "bg-rose-500/90 hover:bg-rose-500"
      : "bg-amber-500/90 hover:bg-amber-500";

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : errorFallback);
      setBusy(false);
      setConfirming(false);
    }
  }

  if (disabled) {
    return (
      <span
        className={`inline-flex items-center rounded-lg border border-neutral-800 ${pad} ${text} text-neutral-600`}
        title={disabledHint}
      >
        {label}
      </span>
    );
  }

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setConfirming(true);
        }}
        className={`inline-flex items-center gap-1.5 rounded-lg border ${outline} ${pad} ${text} font-medium transition`}
      >
        {label}
      </button>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className={`${text} text-neutral-300`}>{confirmLabel}</span>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          run();
        }}
        disabled={busy}
        className={`inline-flex items-center rounded-lg ${solid} ${pad} ${text} font-medium text-white transition disabled:opacity-50`}
      >
        {busy ? busyLabel : confirmActionLabel}
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setConfirming(false);
        }}
        disabled={busy}
        className={`inline-flex items-center rounded-lg border border-neutral-700 ${pad} ${text} text-neutral-300 transition hover:border-neutral-500`}
      >
        Zurück
      </button>
      {error && <span className={`${text} text-rose-400`}>{error}</span>}
    </span>
  );
}
