"use client";

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio } from "@/lib/studio";
import { ErrorBox, Notice, btnCls, cardCls, inputCls, primaryCls } from "./ui";

type Skill = Awaited<ReturnType<typeof studio.skills>>[number];

/** Skill-Registry: nur Anleitungen (Markdown), kein ausführbarer Code. */
export default function SkillsSection() {
  const t = useT();
  const [list, setList] = useState<Skill[]>([]);
  const [url, setUrl] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setList(await studio.skills());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="sk-h" className={`${cardCls} space-y-3`}>
      <h2 id="sk-h" className="text-lg font-semibold text-white">
        {t("sk.title")}
      </h2>
      <Notice>{t("sk.rules")}</Notice>
      <ErrorBox message={error} />
      <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto]">
        <input aria-label="GitHub-URL" placeholder="https://github.com/owner/repo" className={inputCls} value={url} onChange={(e) => setUrl(e.target.value)} />
        <input aria-label={t("sk.path")} placeholder={t("sk.path")} className={inputCls} value={path} onChange={(e) => setPath(e.target.value)} />
        <button type="button" className={primaryCls} disabled={busy || !url} onClick={() => void run(() => studio.importSkillGithub(url, path))}>
          {t("sk.import")}
        </button>
      </div>
      <label className="text-xs text-neutral-400">
        {t("sk.zip")}{" "}
        <input type="file" accept=".zip" disabled={busy} onChange={(e) => e.target.files?.[0] && void run(() => studio.importSkillZip(e.target.files![0]))} />
      </label>
      <ul className="divide-y divide-neutral-800 text-sm">
        {list.map((s) => (
          <li key={s.name} className="space-y-1 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-neutral-100">
                {s.name} <span className="text-xs text-neutral-500">v{s.version} · {s.license ?? "keine Lizenz"} · {s.source.repo ?? s.source.name}{s.source.commit ? `@${s.source.commit}` : ""}
                  {s.author ? ` · von ${s.author}` : ""}
                  {s.requires && s.requires.length ? ` · benötigt: ${s.requires.join(", ")}` : ""}
                  {s.imported_by ? ` · importiert von ${s.imported_by}` : ""}</span>
              </span>
              <span className="flex gap-2">
                <button type="button" className={btnCls} disabled={busy || s.blocked} onClick={() => void run(() => studio.toggleSkill(s.name, !s.enabled))}>
                  {s.enabled ? t("sk.disable") : t("sk.enable")}
                </button>
                <button type="button" className={btnCls} disabled={busy} onClick={() => void run(() => studio.deleteSkill(s.name))}>
                  {t("common.delete")}
                </button>
              </span>
            </div>
            <p className="text-xs text-neutral-400">{s.description}</p>
            {s.warnings.map((w, i) => (
              <p key={i} className="text-xs text-amber-300">
                {w}
              </p>
            ))}
            {s.rejected.length > 0 && <p className="text-[11px] text-neutral-500">{t("sk.rejected")}: {s.rejected.slice(0, 4).join(", ")}{s.rejected.length > 4 ? " …" : ""}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
