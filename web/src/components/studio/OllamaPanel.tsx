"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage, studio } from "@/lib/studio";
import { ErrorBox, btnCls, cardCls } from "./ui";

type Status = Awaited<ReturnType<typeof studio.ollamaStatus>>;
type TestResult = Awaited<ReturnType<typeof studio.ollamaTest>>;

/** Lokales LLM (Ollama) für den KI-Assistenten: Status, Empfehlung, Probelauf.
 *  ClipForge lädt keine Modelle herunter — der Befehl wird nur angezeigt. */
export default function OllamaPanel() {
  const [st, setSt] = useState<Status | null>(null);
  const [test, setTest] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSt(await studio.ollamaStatus());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    studio
      .ollamaStatus()
      .then(setSt)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (!st) return error ? <ErrorBox message={error} /> : null;
  const hw = st.hardware;
  const rec = st.recommendation;
  return (
    <section className={`${cardCls} space-y-2`} aria-label="Ollama">
      <h2 className="text-sm font-semibold text-neutral-200">KI-Assistent lokal (Ollama)</h2>
      <p className="text-xs text-neutral-400">
        Status:{" "}
        <span className={st.reachable ? "text-emerald-400" : "text-amber-400"} data-testid="ollama-status">
          {st.reachable ? `erreichbar (v${st.version})` : "nicht erreichbar"}
        </span>
        {st.reachable && ` · Modell: ${st.model ?? "–"} (${st.model_reason})`}
      </p>
      {st.models.length > 0 && (
        <ul className="text-xs text-neutral-300">
          {st.models.map((m) => (
            <li key={m.name}>
              {m.name} · {m.size_gb} GB · {m.tool_calling ? "Tool-Calling ✓" : "ohne Tool-Calling"}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-neutral-400">
        Rechner: {hw.os} {hw.arch} · {hw.cpus} Kerne · {hw.ram_gb ?? "?"} GB RAM
        {hw.apple_silicon ? " · Apple Silicon" : ""}
        {hw.nvidia_gpu ? " · NVIDIA-GPU" : ""}
      </p>
      {rec.model && (
        <p className="text-xs text-neutral-300">
          Empfehlung: <b>{rec.model}</b> (~{rec.download_gb} GB, {rec.reason}; {rec.acceleration}). Selbst ausführen:{" "}
          <code className="rounded bg-neutral-800 px-1">{rec.command}</code> — {rec.note}
        </p>
      )}
      {st.hint && <p className="text-xs text-amber-300">{st.hint}</p>}
      <div className="flex gap-2">
        <button type="button" className={btnCls} onClick={() => void load()}>
          Neu prüfen
        </button>
        <button
          type="button"
          className={btnCls}
          disabled={busy || !st.reachable || !st.model}
          onClick={async () => {
            setBusy(true);
            setTest(null);
            try {
              setTest(await studio.ollamaTest());
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Teste …" : "Probelauf (Werkzeugaufruf)"}
        </button>
      </div>
      {test && (
        <p className={`text-xs ${test.ok ? "text-emerald-400" : "text-amber-300"}`}>
          {test.ok ? "✓" : "✗"} {test.message}
          {test.seconds != null ? ` · ${test.seconds} s` : ""}
        </p>
      )}
      {error && <ErrorBox message={error} />}
    </section>
  );
}
