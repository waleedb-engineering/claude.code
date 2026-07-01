"use client";

import { useState } from "react";

/**
 * Kleiner destructiver Button mit Inline-Bestätigung.
 * Klick → „Wirklich löschen?" mit Ja/Abbrechen. Kein natives confirm().
 */
export default function DeleteControl({
  onConfirm,
  label = "Löschen",
  confirmLabel = "Wirklich löschen?",
  disabled = false,
  disabledHint,
  size = "sm",
  onDone,
}: {
  onConfirm: () => Promise<void>;
  label?: string;
  confirmLabel?: string;
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

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Löschen fehlgeschlagen.");
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
        className={`inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 ${pad} ${text} font-medium text-rose-300 transition hover:border-rose-500/60 hover:bg-rose-500/10`}
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
        className={`inline-flex items-center rounded-lg bg-rose-500/90 ${pad} ${text} font-medium text-white transition hover:bg-rose-500 disabled:opacity-50`}
      >
        {busy ? "Lösche …" : "Ja, löschen"}
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
        Abbrechen
      </button>
      {error && <span className={`${text} text-rose-400`}>{error}</span>}
    </span>
  );
}
