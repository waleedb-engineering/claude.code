"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { tDyn, useLocale, useT, type TKey } from "@/lib/i18n";
import { errorMessage, studio, type Overview, type ProjectSummary } from "@/lib/studio";
import { ErrorBox, Loading, Pill, btnCls, cardCls, fmtDate, primaryCls } from "@/components/studio/ui";

export default function StudioDashboard() {
  const t = useT();
  const locale = useLocale();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, p] = await Promise.all([studio.overview(), studio.projects()]);
      setOverview(o);
      setProjects(p);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    const timer = setInterval(load, 5000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [load]);

  async function remove(id: string) {
    if (!window.confirm(t("dash.confirm_delete"))) return;
    try {
      await studio.deleteProject(id);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">{t("dash.title")}</h1>
          <p className="mt-1 text-sm text-neutral-300">{t("dash.subtitle")}</p>
        </div>
        <Link href="/studio/create" className={primaryCls}>
          + {t("dash.new")}
        </Link>
      </div>

      <ErrorBox message={error} />

      {overview && (
        <ul className="flex flex-wrap gap-2 text-xs text-neutral-300">
          <li className="rounded-full border border-neutral-700 px-3 py-1">
            {overview.llm_available ? t("dash.llm_on") : t("dash.llm_off")}
          </li>
          <li className="rounded-full border border-neutral-700 px-3 py-1">
            {overview.worker.running ? t("dash.worker_on") : t("dash.worker_off")}
          </li>
        </ul>
      )}

      <section aria-labelledby="projects-heading">
        <h2 id="projects-heading" className="mb-3 text-lg font-semibold text-white">
          {t("dash.projects")}
        </h2>
        {projects === null && !error && <Loading />}
        {projects !== null && projects.length === 0 && (
          <div className={`${cardCls} text-sm text-neutral-300`}>{t("dash.empty")}</div>
        )}
        <ul className="grid gap-3 sm:grid-cols-2">
          {(projects ?? []).map((p) => (
            <li key={p.id} className={cardCls}>
              <div className="flex items-start justify-between gap-3">
                <Link
                  href={`/studio/projects/${p.id}`}
                  className="min-w-0 font-medium text-white hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  <span className="block truncate">{p.title}</span>
                </Link>
                <Pill status={p.status} />
              </div>
              <p className="mt-1 text-xs text-neutral-400">
                {tDyn(t, "wf", p.workflow)} · {p.aspect_ratio} · {p.scene_count} {t("dash.scenes")} · {p.export_count}{" "}
                {t("dash.exports")}
              </p>
              <p className="mt-1 text-xs text-neutral-500">{fmtDate(p.updated_at, locale)}</p>
              {p.status === "failed" && p.status_error && (
                <p className="mt-2 text-xs text-rose-300">{p.status_error.message}</p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link href={`/studio/projects/${p.id}`} className={btnCls}>
                  {t("common.open" as TKey)}
                </Link>
                {p.linked_job_id && (
                  <Link href={`/jobs/${p.linked_job_id}`} className={btnCls}>
                    {t("dash.shorts_job")}
                  </Link>
                )}
                <button type="button" className={btnCls} onClick={() => remove(p.id)}>
                  {t("common.delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
