"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PublishControls from "@/components/studio/PublishControls";
import { useLocale, useT } from "@/lib/i18n";
import { errorMessage, studio, type AnalyticsOverview, type AnalyticsRow, type DraftState } from "@/lib/studio";
import { ErrorBox, Loading, Notice, Pill, btnCls, cardCls, fmtDate, inputCls, labelCls } from "@/components/studio/ui";

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
}

function MetricsForm({ row, onDone, onError }: { row: AnalyticsRow; onDone: () => void; onError: (m: string) => void }) {
  const t = useT();
  const [v, setV] = useState({ views: "", likes: "", comments: "", shares: "", reach: "", saves: "" });
  const pid = row.publishing_id;
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await studio.addMetrics(row.job_id, pid, {
            views: num(v.views),
            likes: num(v.likes),
            comments: num(v.comments),
            shares: num(v.shares),
            reach: num(v.reach),
            saves: num(v.saves),
          });
          setV({ views: "", likes: "", comments: "", shares: "", reach: "", saves: "" });
          onDone();
        } catch (err) {
          onError(errorMessage(err));
        }
      }}
    >
      {(["views", "likes", "comments", "shares", "reach", "saves"] as const).map((f) => (
        <div key={f} className="w-24">
          <label htmlFor={`m-${pid}-${f}`} className={labelCls}>
            {t(`an.${f}`)}
          </label>
          <input
            id={`m-${pid}-${f}`}
            type="number"
            min={0}
            className={inputCls}
            value={v[f]}
            onChange={(e) => setV({ ...v, [f]: e.target.value })}
          />
        </div>
      ))}
      <button type="submit" className={btnCls}>
        {t("an.enter")}
      </button>
      <button
        type="button"
        className={btnCls}
        onClick={async () => {
          try {
            await studio.syncMetrics(row.job_id, pid);
            onDone();
          } catch (err) {
            onError(errorMessage(err));
          }
        }}
      >
        {t("an.sync")}
      </button>
    </form>
  );
}

export default function AnalyticsPage() {
  const t = useT();
  const locale = useLocale();
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [drafts, setDrafts] = useState<DraftState[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, d] = await Promise.all([studio.analytics(), studio.drafts()]);
      setData(a);
      setDrafts(d);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  const value = (n: number | null | undefined) => (n === null || n === undefined ? t("an.noData") : n.toLocaleString(locale));
  const open = drafts.filter((d) => d.state !== "published");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">{t("an.title")}</h1>
        <p className="mt-1 text-sm text-neutral-300">{t("an.subtitle")}</p>
      </div>
      <ErrorBox message={error} />
      {data === null && !error && <Loading />}

      {data && (
        <p className="text-xs text-neutral-300">
          <strong>{t("an.manual")}</strong>: {data.legend.manual} · <strong>{t("an.synced")}</strong>: {data.legend.synced} ·{" "}
          <strong>{t("an.estimated")}</strong>: {data.legend.estimated}
        </p>
      )}

      {data && data.rows.length === 0 && <p className={`${cardCls} text-sm text-neutral-300`}>{t("an.empty")}</p>}
      <ul className="space-y-3">
        {(data?.rows ?? []).map((row) => (
          <li key={row.publishing_id} className={cardCls}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium text-white">{row.title || row.publishing_id}</p>
                <p className="text-xs text-neutral-400">
                  {row.platform} · {fmtDate(row.published_at, locale)} ·{" "}
                  {row.publish_source === "manual" ? t("an.manual") : row.publish_source}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {row.external_url && (
                  <a href={row.external_url} target="_blank" rel="noopener noreferrer" className={btnCls}>
                    ↗ Post
                  </a>
                )}
                {row.studio_project_id && (
                  <Link href={`/studio/projects/${row.studio_project_id}`} className={btnCls}>
                    {t("au.project")}
                  </Link>
                )}
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-xs text-neutral-400">
                  {t("an.potential")} ({t("an.estimated")})
                </dt>
                <dd className="text-white">{row.performance_potential ? row.performance_potential.value : t("an.noData")}</dd>
              </div>
              {(["views", "likes", "comments", "shares", "reach", "saves"] as const).map((f) => (
                <div key={f}>
                  <dt className="text-xs text-neutral-400">
                    {t(`an.${f}`)}
                    {row.metrics ? ` (${row.metrics.source === "manual" ? t("an.manual") : t("an.synced")})` : ""}
                  </dt>
                  <dd className="text-white">{value(row.metrics?.[f])}</dd>
                </div>
              ))}
              <div>
                <dt className="text-xs text-neutral-400">{t("an.engagement")}</dt>
                <dd className="text-white">
                  {row.metrics?.engagement_rate != null ? `${(row.metrics.engagement_rate * 100).toFixed(1)} %` : t("an.noData")}
                </dd>
              </div>
            </dl>
            <MetricsForm row={row} onDone={load} onError={setError} />
          </li>
        ))}
      </ul>

      {data && data.hook_comparisons.length > 0 && (
        <section aria-labelledby="an-hooks">
          <h2 id="an-hooks" className="mb-3 text-lg font-semibold text-white">
            {t("an.hooks")}
          </h2>
          <ul className="space-y-3">
            {data.hook_comparisons.map((c) => (
              <li key={c.group} className={cardCls}>
                <ul className="space-y-1 text-sm text-neutral-200">
                  {c.variants.map((v) => (
                    <li key={v.publishing_id} className="flex flex-wrap justify-between gap-3">
                      <span>
                        {v.hook} <span className="text-neutral-500">({v.platform})</span>
                        {c.best_publishing_id === v.publishing_id && (
                          <span className="ml-2 rounded-full border border-emerald-500/40 px-2 text-xs text-emerald-300">{t("an.best")}</span>
                        )}
                      </span>
                      <span>
                        {value(v.views)} {t("an.views")}
                      </span>
                    </li>
                  ))}
                </ul>
                {c.note && <p className="mt-2 text-xs text-neutral-400">{c.note}</p>}
              </li>
            ))}
          </ul>
          {data.potential_vs_actual.rank_agreement !== null && (
            <p className="mt-3 text-sm text-neutral-300">
              {t("an.agreement")}: {Math.round(data.potential_vs_actual.rank_agreement * 100)}% — {data.potential_vs_actual.note}
            </p>
          )}
        </section>
      )}

      <section aria-labelledby="an-drafts">
        <h2 id="an-drafts" className="mb-3 text-lg font-semibold text-white">
          {t("an.drafts")}
        </h2>
        <Notice>{t("an.confirmPublished")}</Notice>
        {open.length === 0 && <p className="mt-3 text-sm text-neutral-400">{t("an.noDrafts")}</p>}
        <ul className="mt-3 space-y-2">
          {open.map((d) => (
            <li key={d.publishing_id} className={`${cardCls} flex flex-wrap items-end justify-between gap-3`}>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-white">{d.title || d.publishing_id}</p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-neutral-400">
                  {d.platform} <Pill status={d.state} />
                  {d.scheduled_at ? fmtDate(d.scheduled_at, locale) : ""}
                  <Link href={`/jobs/${d.job_id}/publishing`} className="underline hover:text-white">
                    Planner
                  </Link>
                </p>
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label htmlFor={`u-${d.publishing_id}`} className={labelCls}>
                    {t("an.postUrl")}
                  </label>
                  <input
                    id={`u-${d.publishing_id}`}
                    type="url"
                    placeholder="https://"
                    className={inputCls}
                    value={urls[d.publishing_id] ?? ""}
                    onChange={(e) => setUrls({ ...urls, [d.publishing_id]: e.target.value })}
                  />
                </div>
                {d.platform === "tiktok" && (d.state === "ready" || d.state === "failed") && (
                  <button
                    type="button"
                    className={btnCls}
                    onClick={async () => {
                      if (!window.confirm(t("an.tiktokConfirm"))) return;
                      try {
                        await studio.tiktokUpload(d.job_id, d.publishing_id);
                        await load();
                      } catch (e) {
                        setError(errorMessage(e));
                      }
                    }}
                  >
                    {t("an.tiktokUpload")}
                  </button>
                )}
                {d.platform === "tiktok" && (d.state === "uploading" || d.state === "in_platform_drafts") && (
                  <button
                    type="button"
                    className={btnCls}
                    onClick={async () => {
                      try {
                        await studio.tiktokStatus(d.job_id, d.publishing_id);
                        await load();
                      } catch (e) {
                        setError(errorMessage(e));
                      }
                    }}
                  >
                    {t("an.refresh")}
                  </button>
                )}
                <PublishControls d={d} onChanged={load} onError={setError} />
                <button
                  type="button"
                  className={btnCls}
                  onClick={async () => {
                    if (!window.confirm(t("an.confirmPublished"))) return;
                    try {
                      await studio.markPublished(d.job_id, d.publishing_id, urls[d.publishing_id] ?? "");
                      await load();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                >
                  {t("an.markPublished")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
