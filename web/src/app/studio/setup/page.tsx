"use client";

import { useCallback, useEffect, useState } from "react";
import { tDyn, useT } from "@/lib/i18n";
import { errorMessage, studio, type CredentialStatus, type PlatformReadiness, type ProviderInfo } from "@/lib/studio";
import { ErrorBox, Loading, Notice, Pill, btnCls, cardCls, inputCls, labelCls } from "@/components/studio/ui";

export default function SetupPage() {
  const t = useT();
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [platforms, setPlatforms] = useState<PlatformReadiness[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [creds, setCreds] = useState<CredentialStatus[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [data, c] = await Promise.all([studio.providers(), studio.credentials()]);
      setProviders(data.providers);
      setPlatforms(data.platforms);
      setCreds(c);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  async function act(provider: string, fn: () => Promise<string>) {
    try {
      const message = await fn();
      setResults((r) => ({ ...r, [provider]: message }));
      await load();
    } catch (e) {
      setResults((r) => ({ ...r, [provider]: errorMessage(e) }));
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-white">{t("su.title")}</h1>
      <Notice>{t("su.secrets")}</Notice>
      <ErrorBox message={error} />
      {providers === null && !error && <Loading />}

      {creds.length > 0 && (
        <section aria-labelledby="su-cred">
          <h2 id="su-cred" className="mb-1 text-lg font-semibold text-white">
            {t("cr.title")}
          </h2>
          <p className="mb-3 text-xs text-neutral-300">{t("cr.hint")}</p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {creds.map((c) => (
              <li key={c.provider} className={cardCls}>
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-white">{c.label}</p>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      c.configured
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                        : "border-neutral-600/50 bg-neutral-700/30 text-neutral-300"
                    }`}
                  >
                    {c.configured ? t("cr.set") : t("cr.unset")}
                  </span>
                </div>
                <form
                  className="mt-3 space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const value = keys[c.provider] ?? "";
                    void act(c.provider, async () => {
                      await studio.setCredential(c.provider, value);
                      setKeys((k) => ({ ...k, [c.provider]: "" }));
                      return t("cr.set");
                    });
                  }}
                >
                  <label htmlFor={`cr-${c.provider}`} className={labelCls}>
                    {t("cr.key")} (<code>{c.env}</code>)
                  </label>
                  <input
                    id={`cr-${c.provider}`}
                    type="password"
                    autoComplete="off"
                    minLength={8}
                    className={inputCls}
                    value={keys[c.provider] ?? ""}
                    onChange={(e) => setKeys({ ...keys, [c.provider]: e.target.value })}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button type="submit" className={btnCls} disabled={(keys[c.provider] ?? "").length < 8}>
                      {t("cr.save")}
                    </button>
                    <button
                      type="button"
                      className={btnCls}
                      disabled={!c.configured}
                      onClick={() => act(c.provider, async () => (await studio.testCredential(c.provider)).message)}
                    >
                      {t("cr.test")}
                    </button>
                    <button
                      type="button"
                      className={btnCls}
                      disabled={!c.configured}
                      onClick={() =>
                        act(c.provider, async () => {
                          await studio.deleteCredential(c.provider);
                          return t("cr.unset");
                        })
                      }
                    >
                      {t("cr.remove")}
                    </button>
                  </div>
                  {results[c.provider] && (
                    <p role="status" aria-live="polite" className="text-xs text-neutral-300">
                      {results[c.provider]}
                    </p>
                  )}
                </form>
              </li>
            ))}
          </ul>
        </section>
      )}

      {providers && (
        <section aria-labelledby="su-prov">
          <h2 id="su-prov" className="mb-3 text-lg font-semibold text-white">
            {t("su.providers")}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {providers.map((p) => (
              <li key={p.id} className={cardCls}>
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-white">{p.label}</p>
                  <Pill status={p.status} />
                </div>
                <p className="mt-1 text-xs text-neutral-400">
                  {p.kind} · {p.local ? t("common.local") : "Cloud"}
                  {p.paid ? ` · ${t("common.paid")}` : ""}
                </p>
                {p.requires_env.length > 0 && (
                  <p className="mt-2 text-xs text-neutral-300">
                    {t("su.needs")}: <code>{p.requires_env.join(", ")}</code>
                  </p>
                )}
                {p.hint && <p className="mt-2 text-xs text-neutral-300">{p.hint}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {platforms.length > 0 && (
        <section aria-labelledby="su-plat">
          <h2 id="su-plat" className="mb-3 text-lg font-semibold text-white">
            {t("su.platforms")}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {platforms.map((p) => (
              <li key={p.platform} className={cardCls}>
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-white">{tDyn(t, "platform", p.platform)}</p>
                  <Pill status={p.state} />
                </div>
                <p className="mt-2 text-xs text-neutral-300">{p.note}</p>
                {p.setup_steps.length > 0 && (
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-neutral-300">
                    {p.setup_steps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ol>
                )}
                <p className="mt-2 text-xs text-neutral-400">{t("su.fallback")}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
