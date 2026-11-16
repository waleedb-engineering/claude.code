"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useLocale, useT } from "@/lib/i18n";
import { errorMessage, studio, type Idea } from "@/lib/studio";
import { ErrorBox, Loading, Notice, btnCls, cardCls, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

type Options = { hook_types: string[]; formats: string[]; platforms: string[] };
const EMPTY = { title: "", url: "", notes: "", niche: "", tags: "", hook_type: "other", format: "other", platform: "other", views: "" };

export default function IdeasPage() {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [options, setOptions] = useState<Options>({ hook_types: [], formats: [], platforms: [] });
  const [notice, setNotice] = useState("");
  const [filters, setFilters] = useState({ q: "", hook_type: "", format: "", platform: "", niche: "" });
  const [form, setForm] = useState(EMPTY);
  const [topics, setTopics] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const qs = Object.entries(filters)
      .filter(([, v]) => v)
      .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
      .join("&");
    try {
      const data = await studio.ideas(qs);
      setIdeas(data.ideas);
      setOptions(data.options);
      setNotice(data.notice[locale] ?? data.notice.de);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [filters, locale]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await studio.createIdea({
        title: form.title,
        url: form.url,
        notes: form.notes,
        niche: form.niche,
        tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean),
        hook_type: form.hook_type,
        format: form.format,
        platform: form.platform,
        metrics: form.views ? { views: Number(form.views) } : undefined,
      });
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const select = (id: string, label: string, value: string, list: string[], onChange: (v: string) => void, withAll: boolean) => (
    <div>
      <label htmlFor={id} className={labelCls}>
        {label}
      </label>
      <select id={id} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        {withAll && <option value="">{t("id.all")}</option>}
        {list.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">{t("id.title")}</h1>
        <p className="mt-1 text-sm text-neutral-300">{t("id.subtitle")}</p>
      </div>
      {notice && <Notice>{notice}</Notice>}
      <ErrorBox message={error} />

      <form onSubmit={add} className={`${cardCls} grid gap-3 sm:grid-cols-2 lg:grid-cols-4`}>
        <div className="sm:col-span-2">
          <label htmlFor="i-title" className={labelCls}>
            {t("id.titleField")}
          </label>
          <input id="i-title" className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="i-url" className={labelCls}>
            URL
          </label>
          <input id="i-url" type="url" placeholder="https://" className={inputCls} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </div>
        <div>
          <label htmlFor="i-niche" className={labelCls}>
            {t("id.niche")}
          </label>
          <input id="i-niche" className={inputCls} value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} />
        </div>
        <div>
          <label htmlFor="i-tags" className={labelCls}>
            {t("id.tags")}
          </label>
          <input id="i-tags" className={inputCls} value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </div>
        {select("i-hook", t("id.hook"), form.hook_type, options.hook_types, (v) => setForm({ ...form, hook_type: v }), false)}
        {select("i-format", t("id.format"), form.format, options.formats, (v) => setForm({ ...form, format: v }), false)}
        {select("i-platform", t("id.platform"), form.platform, options.platforms, (v) => setForm({ ...form, platform: v }), false)}
        <div>
          <label htmlFor="i-views" className={labelCls}>
            {t("an.views")} ({t("an.manual")})
          </label>
          <input id="i-views" type="number" min={0} className={inputCls} value={form.views} onChange={(e) => setForm({ ...form, views: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="i-notes" className={labelCls}>
            {t("id.notes")}
          </label>
          <input id="i-notes" className={inputCls} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div className="sm:col-span-2 lg:col-span-4">
          <button type="submit" className={primaryCls} disabled={!form.title.trim() && !form.url.trim()}>
            {t("id.add")}
          </button>
        </div>
      </form>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" role="search">
        <div>
          <label htmlFor="f-q" className={labelCls}>
            {t("id.search")}
          </label>
          <input id="f-q" type="search" className={inputCls} value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        </div>
        <div>
          <label htmlFor="f-niche" className={labelCls}>
            {t("id.niche")}
          </label>
          <input id="f-niche" className={inputCls} value={filters.niche} onChange={(e) => setFilters({ ...filters, niche: e.target.value })} />
        </div>
        {select("f-hook", t("id.hook"), filters.hook_type, options.hook_types, (v) => setFilters({ ...filters, hook_type: v }), true)}
        {select("f-format", t("id.format"), filters.format, options.formats, (v) => setFilters({ ...filters, format: v }), true)}
        {select("f-platform", t("id.platform"), filters.platform, options.platforms, (v) => setFilters({ ...filters, platform: v }), true)}
      </div>

      {ideas === null && !error && <Loading />}
      {ideas !== null && ideas.length === 0 && <p className={`${cardCls} text-sm text-neutral-300`}>{t("id.empty")}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {(ideas ?? []).map((idea) => (
          <li key={idea.id} className={cardCls}>
            <p className="font-medium text-white">{idea.title}</p>
            {idea.url && (
              <a href={idea.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs text-indigo-300 underline">
                {idea.url}
              </a>
            )}
            <p className="mt-1 text-xs text-neutral-400">
              {[idea.niche, idea.hook_type, idea.format, idea.platform].filter(Boolean).join(" · ")}
              {idea.metrics.views !== null ? ` · ${idea.metrics.views.toLocaleString(locale)} ${t("an.views")} (${t("an.manual")})` : ""}
            </p>
            {idea.tags.length > 0 && <p className="mt-1 text-xs text-neutral-300">#{idea.tags.join(" #")}</p>}
            {idea.notes && <p className="mt-2 text-sm text-neutral-200">{idea.notes}</p>}
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <div className="min-w-40 flex-1">
                <label htmlFor={`t-${idea.id}`} className={labelCls}>
                  {t("id.topic")}
                </label>
                <input
                  id={`t-${idea.id}`}
                  className={inputCls}
                  value={topics[idea.id] ?? ""}
                  onChange={(e) => setTopics({ ...topics, [idea.id]: e.target.value })}
                />
              </div>
              <button
                type="button"
                className={btnCls}
                disabled={(topics[idea.id] ?? "").trim().length < 3}
                onClick={async () => {
                  try {
                    const res = await studio.useIdea(idea.id, topics[idea.id], locale);
                    router.push(`/studio/projects/${res.project.id}`);
                  } catch (e) {
                    setError(errorMessage(e));
                  }
                }}
              >
                {t("id.use")}
              </button>
              <button
                type="button"
                className={btnCls}
                aria-label={`${t("common.delete")}: ${idea.title}`}
                onClick={async () => {
                  try {
                    await studio.deleteIdea(idea.id);
                    await load();
                  } catch (e) {
                    setError(errorMessage(e));
                  }
                }}
              >
                {t("common.delete")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
