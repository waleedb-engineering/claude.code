export default function Disclaimer({ text }: { text?: string }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-neutral-800 bg-neutral-900/40 px-4 py-3 text-xs text-neutral-400">
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-neutral-500"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8h.01M11 12h1v4h1" strokeLinecap="round" />
      </svg>
      <span>
        {text ??
          "Der Performance-Potential-Score ist eine Wahrscheinlichkeits-Einschätzung auf Basis messbarer Signale und keine Garantie für Reichweite oder Viralität."}
      </span>
    </p>
  );
}
