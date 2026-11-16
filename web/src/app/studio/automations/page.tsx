"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { tDyn, useLocale, useT } from "@/lib/i18n";
import { errorMessage, studio, type Automation } from "@/lib/studio";
import { ErrorBox, Loading, Notice, Pill, btnCls, cardCls, fmtDate, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

const WORKFLOWS = ["prompt", "script", "article_url", "website_review", "social_url", "cinematic"];
const PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "x"];
const WEEKDAYS = { de: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] };

export default function AutomationsPage() {
  const t = useT();
  const locale = useLocale();
  const [list, setList] = useState<Automation[] | null>(null);
  const [workerRunning, setWorkerRunning] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    workflow: "prompt",
    frequency: "daily",
    time: "09:00",
    weekday: 0,
    day: 1,
    items: "",
    language: "de",
    platforms: [] as string[],
    budgetRun: 0,
    budgetMonth: 0,
  });

  const load = useCallback(async () => {
    try {
      const data = await studio.automations();
      setList(data.automations);
      setWorkerRunning(data.worker.running);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    const timer = setInterval(load, 4000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    await act(async () => {
      await studio.createAutomation({
        name: form.name,
        workflow: form.workflow,
        language: form.language,
        items: form.items.split("\n").filter((l) => l.trim()),
        schedule: {
          frequency: form.frequency,
          time: form.time,
          weekday: form.weekday,
          day: form.day,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        },
        publishing: { mode: form.platforms.length ? "draft" : "none", platforms: form.platforms },
        budget_per_run_usd: form.budgetRun,
        monthly_budget_usd: form.budgetMonth,
      });
      setShowForm(false);
    });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-white">{t("au.title")}</h1>
        <button type="button" className={primaryCls} aria-expanded={showForm} onClick={() => setShowForm(!showForm)}>
          + {t("au.new")}
        </button>
      </div>
      <Notice>{t("au.safety")}</Notice>
      {!workerRunning && list !== null && <Notice>{t("dash.worker_off")}</Notice>}
      <ErrorBox message={error} />

      {showForm && (
        <form onSubmit={create} className={`${cardCls} grid gap-3 sm:grid-cols-2`}>
          <div>
            <label htmlFor="a-name" className={labelCls}>
              {t("au.name")}
            </label>
            <input id="a-name" required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label htmlFor="a-wf" className={labelCls}>
              Workflow
            </label>
            <select id="a-wf" className={inputCls} value={form.workflow} onChange={(e) => setForm({ ...form, workflow: e.target.value })}>
              {WORKFLOWS.map((w) => (
                <option key={w} value={w}>
                  {tDyn(t, "wf", w)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="a-freq" className={labelCls}>
              {t("au.frequency")}
            </label>
            <select id="a-freq" className={inputCls} value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
              <option value="daily">{t("au.daily")}</option>
              <option value="weekly">{t("au.weekly")}</option>
              <option value="monthly">{t("au.monthly")}</option>
            </select>
          </div>
          <div>
            <label htmlFor="a-time" className={labelCls}>
              {t("au.time")}
            </label>
            <input id="a-time" type="time" required className={inputCls} value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
          </div>
          {form.frequency === "weekly" && (
            <div>
              <label htmlFor="a-wd" className={labelCls}>
                {t("au.weekday")}
              </label>
              <select id="a-wd" className={inputCls} value={form.weekday} onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}>
                {WEEKDAYS[locale].map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          )}
          {form.frequency === "monthly" && (
            <div>
              <label htmlFor="a-day" className={labelCls}>
                {t("au.day")}
              </label>
              <input
                id="a-day"
                type="number"
                min={1}
                max={31}
                className={inputCls}
                value={form.day}
                onChange={(e) => setForm({ ...form, day: Number(e.target.value) || 1 })}
              />
            </div>
          )}
          <div>
            <label htmlFor="a-lang" className={labelCls}>
              {t("common.language")}
            </label>
            <select id="a-lang" className={inputCls} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="a-items" className={labelCls}>
              {t("au.items")}
            </label>
            <textarea
              id="a-items"
              required
              className={`${inputCls} min-h-24`}
              value={form.items}
              onChange={(e) => setForm({ ...form, items: e.target.value })}
            />
          </div>
          <fieldset className="sm:col-span-2">
            <legend className={labelCls}>{t("au.drafts")}</legend>
            <div className="flex flex-wrap gap-3 text-sm text-neutral-200">
              {PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="accent-indigo-400"
                    checked={form.platforms.includes(p)}
                    onChange={(e) =>
                      setForm({ ...form, platforms: e.target.checked ? [...form.platforms, p] : form.platforms.filter((x) => x !== p) })
                    }
                  />
                  {p}
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label htmlFor="a-br" className={labelCls}>
              {t("au.budgetRun")}
            </label>
            <input
              id="a-br"
              type="number"
              min={0}
              step={0.5}
              className={inputCls}
              value={form.budgetRun}
              onChange={(e) => setForm({ ...form, budgetRun: Number(e.target.value) || 0 })}
            />
          </div>
          <div>
            <label htmlFor="a-bm" className={labelCls}>
              {t("au.budgetMonth")}
            </label>
            <input
              id="a-bm"
              type="number"
              min={0}
              step={1}
              className={inputCls}
              value={form.budgetMonth}
              onChange={(e) => setForm({ ...form, budgetMonth: Number(e.target.value) || 0 })}
            />
          </div>
          <div className="sm:col-span-2">
            <button type="submit" className={primaryCls}>
              {t("au.create")}
            </button>
          </div>
        </form>
      )}

      {list === null && !error && <Loading />}
      {list !== null && list.length === 0 && <p className={`${cardCls} text-sm text-neutral-300`}>{t("au.empty")}</p>}
      <ul className="space-y-3">
        {(list ?? []).map((a) => (
          <li key={a.id} className={cardCls}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium text-white">{a.name}</p>
                <p className="text-xs text-neutral-400">
                  {tDyn(t, "wf", a.workflow)} · {t(`au.${a.schedule.frequency}` as "au.daily")} {a.schedule.time} ({a.schedule.timezone}) ·{" "}
                  {a.items.length} Items · {a.publishing.mode === "draft" ? a.publishing.platforms.join(", ") : "–"}
                </p>
                <p className="mt-1 text-xs text-neutral-300">
                  {a.enabled ? `${t("au.next")}: ${fmtDate(a.next_run_at, locale)}` : t("au.paused")}
                  {a.monthly_budget_usd > 0 ? ` · ${a.month_spend_usd.toFixed(2)}/${a.monthly_budget_usd.toFixed(2)} USD` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnCls} disabled={a.active} onClick={() => act(() => studio.automationAction(a.id, "run"))}>
                  {t("au.runNow")}
                </button>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() => act(() => studio.automationAction(a.id, a.enabled ? "pause" : "resume"))}
                >
                  {a.enabled ? t("au.pause") : t("au.resume")}
                </button>
                <button type="button" className={btnCls} disabled={a.active} onClick={() => act(() => studio.deleteAutomation(a.id))}>
                  {t("common.delete")}
                </button>
              </div>
            </div>
            <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">{t("au.history")}</h3>
            {a.runs.length === 0 ? (
              <p className="mt-1 text-xs text-neutral-400">{t("au.noRuns")}</p>
            ) : (
              <ul className="mt-1 space-y-1 text-xs text-neutral-300">
                {a.runs.slice(0, 6).map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-2">
                    <Pill status={r.status} />
                    <span>{fmtDate(r.started_at ?? r.scheduled_for, locale)}</span>
                    <span className="text-neutral-500">
                      {r.trigger} · #{r.attempt}
                    </span>
                    {r.project_id && (
                      <Link href={`/studio/projects/${r.project_id}`} className="underline hover:text-white">
                        {t("au.project")}
                      </Link>
                    )}
                    {r.error && <span className="text-rose-300">{r.error.message}</span>}
                    {(r.status === "failed" || r.status === "interrupted") && !r.retried && (
                      <button type="button" className="underline hover:text-white" onClick={() => act(() => studio.retryRun(a.id, r.id))}>
                        {t("common.retry")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
