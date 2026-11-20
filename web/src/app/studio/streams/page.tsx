"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, type StreamMeta } from "@/lib/studio";
import { ErrorBox, Notice, cardCls, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

export default function StreamsPage() {
  const t = useT();
  const router = useRouter();
  const [list, setList] = useState<StreamMeta[] | null>(null);
  const [form, setForm] = useState({ title: "", platform: "twitch", rights: false });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setList(await studio.streams());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const s = await studio.createStream({ title: form.title, platform: form.platform, rights_confirmed: form.rights });
      router.push(`/studio/streams/${s.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">{t("st.title")}</h1>
        <p className="mt-1 text-sm text-neutral-300">{t("st.hint")}</p>
      </div>
      <ErrorBox message={error} />
      <form onSubmit={create} className={`${cardCls} grid gap-3 sm:grid-cols-3`}>
        <h2 className="text-sm font-semibold text-neutral-200 sm:col-span-3">{t("st.new")}</h2>
        <div>
          <label htmlFor="s-title" className={labelCls}>
            Titel
          </label>
          <input id="s-title" className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div>
          <label htmlFor="s-platform" className={labelCls}>
            {t("st.platform")}
          </label>
          <select id="s-platform" className={inputCls} value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
            <option value="twitch">Twitch</option>
            <option value="youtube">YouTube</option>
            <option value="kick">Kick</option>
            <option value="obs">OBS-Aufnahme</option>
            <option value="upload">Upload</option>
          </select>
        </div>
        <label className="flex items-start gap-2 text-sm text-neutral-200 sm:col-span-3">
          <input type="checkbox" className="mt-1 accent-indigo-400" checked={form.rights} onChange={(e) => setForm({ ...form, rights: e.target.checked })} />
          {t("st.rights")}
        </label>
        <div>
          <button type="submit" className={primaryCls} disabled={!form.rights}>
            {t("st.create")}
          </button>
        </div>
      </form>
      {list && list.length === 0 && <Notice>{t("st.none")}</Notice>}
      <ul className="space-y-2">
        {(list ?? []).map((s) => (
          <li key={s.id} className={cardCls}>
            <Link href={`/studio/streams/${s.id}`} className="font-medium text-white hover:underline">
              {s.title}
            </Link>
            <p className="text-xs text-neutral-400">
              {s.platform} · {s.status}
              {s.video ? ` · ${Math.round(s.video.duration / 60)} min` : ""}
              {s.chat ? ` · ${s.chat.messages} Chat-Nachrichten` : ""}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
