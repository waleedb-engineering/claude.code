"use client";

import { useCallback, useEffect, useState } from "react";
import { useT, type TKey } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type LocalModel } from "@/lib/studio";
import { ErrorBox, btnCls, cardCls } from "./ui";

const GROUPS = ["piper", "translate", "background", "face"] as const;

/** Lokale Modelle laden/löschen — Download nur nach ausdrücklicher Bestätigung. */
export default function ModelsSection() {
  const t = useT();
  const [models, setModels] = useState<LocalModel[]>([]);
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [hw, setHw] = useState<Awaited<ReturnType<typeof studio.hardware>> | null>(null);

  const load = useCallback(async () => {
    try {
      setModels(await studio.models());
      setHw(await studio.hardware());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  async function download(m: LocalModel) {
    if (!window.confirm(`${t("models.confirm")}\n\n${m.label}\n${t("models.license")}: ${m.license}\n~${m.size_mb} MB`)) return;
    setError(null);
    setBusy((b) => ({ ...b, [m.id]: "…" }));
    try {
      const task = await studio.downloadModel(m.id);
      const done = await waitForTask(task.id, (tk) =>
        setBusy((b) => ({ ...b, [m.id]: tk.progress[tk.progress.length - 1] ?? "…" })),
      );
      if (done.status !== "succeeded") throw new Error(done.error?.message ?? "Download fehlgeschlagen.");
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy((b) => {
        const next = { ...b };
        delete next[m.id];
        return next;
      });
    }
  }

  async function remove(m: LocalModel) {
    try {
      await studio.deleteModel(m.id);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <section id="models" aria-labelledby="su-models" className={`${cardCls} space-y-3`}>
      <h2 id="su-models" className="text-lg font-semibold text-white">
        {t("models.title")}
      </h2>
      <p className="text-sm text-neutral-300">{t("models.hint")}</p>
      <ErrorBox message={error} />
      {hw && (
        <div className="rounded-xl border border-neutral-800 p-3 text-xs text-neutral-300">
          <p className="font-semibold text-neutral-200">{t("models.localVideo")}</p>
          <p>
            {hw.system} · {hw.nvidia_gpus.map((g) => `${g.name} (${g.vram_gb} GB)`).join(", ") || (hw.apple_silicon ? "Apple Silicon" : t("models.noGpu"))}
            {hw.ram_gb ? ` · ${hw.ram_gb} GB RAM` : ""}
          </p>
          <p className={hw.local_ai_video === "unsuitable" ? "text-amber-300" : "text-emerald-300"}>{hw.note}</p>
          <p>
            {t("models.notBuiltIn")} {t("models.freeAlt")}: {hw.free_alternatives.join(", ")}. {hw.paid_alternative}.
          </p>
        </div>
      )}
      {GROUPS.map((g) => (
        <div key={g} className="space-y-1">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">{t(`models.group.${g}` as TKey)}</h3>
          <ul className="divide-y divide-neutral-800 text-sm">
            {models
              .filter((m) => m.group === g)
              .map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div>
                    <p className="text-neutral-100">
                      {m.label} <span className="text-xs text-neutral-500">~{m.size_mb} MB</span>
                    </p>
                    <p className="text-xs text-neutral-400">
                      {t("models.license")}: {m.license}
                      {m.commercial_use === false && <span className="text-amber-300"> · {t("models.commercialNo")}</span>}
                      {m.commercial_use === null && <span className="text-amber-300"> · {t("models.commercialUnknown")}</span>}
                    </p>
                  </div>
                  {busy[m.id] ? (
                    <span role="status" className="text-xs text-indigo-300">
                      {busy[m.id]}
                    </span>
                  ) : m.installed ? (
                    <span className="flex items-center gap-2 text-xs text-emerald-300">
                      ✓ {t("models.installed")}
                      <button type="button" className={btnCls} onClick={() => void remove(m)}>
                        {t("common.delete")}
                      </button>
                    </span>
                  ) : (
                    <button type="button" className={btnCls} onClick={() => void download(m)}>
                      {t("models.download")}
                    </button>
                  )}
                </li>
              ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
