"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type AgentMessage } from "@/lib/studio";
import { btnCls, cardCls, inputCls, primaryCls } from "./ui";

type Props = {
  kind: "project" | "stream";
  targetId: string;
  /** vor dem Ausführen: ungespeicherte Editor-Änderungen sichern (ein Zustand) */
  beforeExecute?: () => Promise<boolean>;
  /** nach Änderungen: Editor neu laden */
  onChanged?: () => void;
};

/** KI-Chat zur Bearbeitung: Befehl → Plan → Bestätigen → Ausführen → Rückgängig. */
export default function AgentChat({ kind, targetId, beforeExecute, onChanged }: Props) {
  const t = useT();
  const [msgs, setMsgs] = useState<AgentMessage[]>([]);
  const [engines, setEngines] = useState<{ id: string; label: string; ready: boolean; paid: boolean; hint?: string; cost_per_message_usd?: number | null; model?: string }[]>([]);
  const [engine, setEngine] = useState("rules");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const endRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      setMsgs(await studio.agentHistory(kind, targetId));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [kind, targetId]);

  useEffect(() => {
    const first = setTimeout(async () => {
      await load();
      try {
        setEngines((await studio.agentEngines()).engines);
      } catch {
        /* Engines optional */
      }
    }, 0);
    return () => clearTimeout(first);
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [msgs.length]);

  const current = engines.find((e) => e.id === engine);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setError(null);
    let confirmCost = false;
    if (current?.paid) {
      confirmCost = window.confirm(
        current.cost_per_message_usd != null
          ? `${current.label}: ca. ${current.cost_per_message_usd} USD je Nachricht (Projektbudget). Senden?`
          : `${current.label}: Kosten hängen von deinem Anbieter-Tarif ab (evtl. Gratis-Kontingent). Senden?`,
      );
      if (!confirmCost) return;
    }
    setBusy(t("ag.thinking"));
    try {
      await studio.agentSend(kind, targetId, text, engine, confirmCost);
      setText("");
      await load();
    } catch (err) {
      setError(errorMessage(err));
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function execute(m: AgentMessage) {
    setError(null);
    setBusy(t("ag.running"));
    try {
      if (beforeExecute && !(await beforeExecute())) throw new Error(t("ag.saveFirst"));
      const res = await studio.agentExecute(kind, targetId, m.id, !!confirmed[m.id]);
      await load();
      onChanged?.();
      for (const r of res.plan?.results ?? []) {
        if (r.task_id) {
          setBusy(t("ag.waiting"));
          await waitForTask(r.task_id, (tk) => setBusy(tk.progress[tk.progress.length - 1] ?? t("ag.waiting")));
          onChanged?.();
        }
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className={`${cardCls} flex max-h-[70vh] flex-col gap-2`} aria-labelledby={`ag-${targetId}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={`ag-${targetId}`} className="text-sm font-semibold text-neutral-200">
          {t("ag.title")}
        </h2>
        <select aria-label={t("ag.engine")} className={`${inputCls} w-auto text-xs`} value={engine} onChange={(e) => setEngine(e.target.value)}>
          {engines.map((en) => (
            <option key={en.id} value={en.id} disabled={!en.ready}>
              {en.label}
              {en.ready ? "" : ` · ${t("status.not_configured")}`}
            </option>
          ))}
          {engines.length === 0 && <option value="rules">Regelbasiert</option>}
        </select>
      </div>
      <div className="min-h-24 flex-1 space-y-2 overflow-y-auto text-sm" aria-live="polite">
        {msgs.length === 0 && <p className="text-xs text-neutral-400">{kind === "project" ? t("ag.examplesProject") : t("ag.examplesStream")}</p>}
        {msgs.map((m) => (
          <div key={m.id} className={m.role === "user" ? "ml-6 rounded-lg bg-indigo-500/15 p-2 text-neutral-100" : "mr-6 rounded-lg bg-neutral-800/60 p-2 text-neutral-200"}>
            <p>{m.text}</p>
            {(m.notes ?? []).map((n, i) => (
              <p key={i} className="mt-1 text-xs text-amber-300">
                {n}
              </p>
            ))}
            {m.plan && m.plan.steps.length > 0 && (
              <div className="mt-1 space-y-1">
                <ol className="list-decimal pl-5 text-xs text-neutral-300">
                  {m.plan.steps.map((s, i) => {
                    const res = m.plan?.results?.[i];
                    return (
                      <li key={i}>
                        <code className="text-indigo-300">{s.tool}</code> {JSON.stringify(s.args)}
                        {res &&
                          (res.ok ? (
                            <span className="text-emerald-300"> ✓ {res.change ?? ""}</span>
                          ) : res.status === "skipped" ? (
                            <span className="text-neutral-500"> – übersprungen (vorheriger Schritt fehlgeschlagen)</span>
                          ) : (
                            <span className="text-rose-300"> ✗ {res.error}</span>
                          ))}
                      </li>
                    );
                  })}
                </ol>
                {m.plan.status === "pending" && (
                  <div className="flex flex-wrap items-center gap-2">
                    {m.plan.needs_confirmation && (
                      <label className="flex items-center gap-1 text-xs text-amber-200">
                        <input type="checkbox" checked={!!confirmed[m.id]} onChange={(e) => setConfirmed({ ...confirmed, [m.id]: e.target.checked })} />
                        {t("ag.confirmRender")}
                      </label>
                    )}
                    <button type="button" className={primaryCls} disabled={!!busy || (m.plan.needs_confirmation && !confirmed[m.id])} onClick={() => void execute(m)}>
                      {t("ag.execute")}
                    </button>
                    <button
                      type="button"
                      className={btnCls}
                      disabled={!!busy}
                      onClick={async () => {
                        await studio.agentDiscard(kind, targetId, m.id);
                        await load();
                      }}
                    >
                      {t("ag.discard")}
                    </button>
                  </div>
                )}
                {m.plan.status !== "pending" && <p className="text-[11px] text-neutral-500">{m.plan.undone ? t("ag.undone") : m.plan.status}</p>}
                {m.plan.status === "partial" && !m.plan.undone && (
                  <button
                    type="button"
                    className={btnCls}
                    disabled={!!busy}
                    onClick={async () => {
                      setError(null);
                      try {
                        if (beforeExecute && !(await beforeExecute())) return;
                        await studio.agentRetry(kind, targetId, m.id, true);
                        await load();
                        onChanged?.();
                      } catch (err) {
                        setError(errorMessage(err));
                      }
                    }}
                  >
                    ↻ Ab dem Fehler wiederholen
                  </button>
                )}
                {(m.plan.results ?? []).some((r) => r.task_id) && m.plan.status !== "pending" && (
                  <button
                    type="button"
                    className={btnCls}
                    onClick={async () => {
                      try {
                        await studio.agentCancel(kind, targetId, m.id);
                        await load();
                      } catch (err) {
                        setError(errorMessage(err));
                      }
                    }}
                  >
                    ■ Gestartete Aufgaben abbrechen
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {busy && (
        <p role="status" className="text-xs text-indigo-300">
          {busy}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}
      <form onSubmit={send} className="flex gap-2">
        <input aria-label={t("ag.input")} placeholder={t("ag.input")} className={inputCls} value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy} />
        <button type="submit" className={primaryCls} disabled={!!busy || !text.trim()}>
          {t("ag.send")}
        </button>
      </form>
      {kind === "project" && (
        <button
          type="button"
          className={`${btnCls} self-start text-xs`}
          disabled={!!busy}
          onClick={async () => {
            setError(null);
            try {
              await studio.agentUndo(kind, targetId);
              await load();
              onChanged?.();
            } catch (e) {
              setError(errorMessage(e));
            }
          }}
        >
          ↶ {t("ag.undo")}
        </button>
      )}
      {current?.hint && <p className="text-[11px] text-neutral-500">{current.hint}</p>}
    </section>
  );
}
