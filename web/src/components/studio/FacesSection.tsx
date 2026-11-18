"use client";

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio } from "@/lib/studio";
import { ErrorBox, Notice, btnCls, cardCls, inputCls, labelCls, primaryCls } from "./ui";

type Data = Awaited<ReturnType<typeof studio.faces>>;

/** Referenzgesichter für den autorisierten Face Swap (mit Einwilligung). */
export default function FacesSection() {
  const t = useT();
  const [data, setData] = useState<Data | null>(null);
  const [audit, setAudit] = useState<{ at: string; event: string; result?: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", basis: "", person: "", noDeception: false });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await studio.faces();
      setData(d);
      if (d.enabled) setAudit((await studio.faceAudit()).entries.slice(-10).reverse());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  if (!data) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", form.name);
      fd.append("basis", form.basis);
      fd.append("person", form.person);
      fd.append("no_deception", String(form.noDeception));
      await studio.registerFace(fd);
      setForm({ name: "", basis: "", person: "", noDeception: false });
      setFile(null);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="fs-h" className={`${cardCls} space-y-3`}>
      <h2 id="fs-h" className="text-lg font-semibold text-white">
        {t("fs.title")}
      </h2>
      <Notice>{t("fs.rules")}</Notice>
      {!data.enabled && <p className="text-sm text-amber-300">{data.reason}</p>}
      <ErrorBox message={error} />
      {data.enabled && (
        <>
          <ul className="space-y-1 text-sm text-neutral-200">
            {data.faces.length === 0 && <li className="text-neutral-400">{t("fs.none")}</li>}
            {data.faces.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2">
                <span>
                  {f.name} <span className="text-xs text-neutral-500">({f.consent.person})</span>
                </span>
                <button
                  type="button"
                  className={btnCls}
                  onClick={async () => {
                    try {
                      await studio.deleteFace(f.id);
                      await load();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                >
                  {t("common.delete")}
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={submit} className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <label htmlFor="fs-name" className={labelCls}>
                  {t("fs.name")}
                </label>
                <input id="fs-name" required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label htmlFor="fs-file" className={labelCls}>
                  {t("fs.photo")}
                </label>
                <input id="fs-file" type="file" accept="image/png,image/jpeg,image/webp" required className={inputCls} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </div>
            </div>
            <fieldset className="space-y-1 text-sm text-neutral-200">
              <label className="flex items-start gap-2">
                <input type="radio" name="fs-basis" className="mt-1" checked={form.basis === "own"} onChange={() => setForm({ ...form, basis: "own" })} />
                {t("fs.own")}
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="fs-basis" className="mt-1" checked={form.basis === "permission"} onChange={() => setForm({ ...form, basis: "permission" })} />
                {t("fs.permission")}
              </label>
              {form.basis === "permission" && (
                <input aria-label={t("fs.person")} placeholder={t("fs.person")} required className={inputCls} value={form.person} onChange={(e) => setForm({ ...form, person: e.target.value })} />
              )}
              <label className="flex items-start gap-2">
                <input type="checkbox" className="mt-1" checked={form.noDeception} onChange={(e) => setForm({ ...form, noDeception: e.target.checked })} />
                {t("fs.noDeception")}
              </label>
            </fieldset>
            <button type="submit" className={primaryCls} disabled={busy || !form.basis || !form.noDeception || !file}>
              {t("fs.register")}
            </button>
          </form>
          {audit.length > 0 && (
            <details className="text-xs text-neutral-400">
              <summary>{t("fs.audit")}</summary>
              <ul>
                {audit.map((a, i) => (
                  <li key={i}>
                    {a.at} · {a.event} {a.result ?? ""}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
