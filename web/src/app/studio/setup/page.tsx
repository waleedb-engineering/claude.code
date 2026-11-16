"use client";

import { useEffect, useState } from "react";
import { tDyn, useT } from "@/lib/i18n";
import { errorMessage, studio, type PlatformReadiness, type ProviderInfo } from "@/lib/studio";
import { ErrorBox, Loading, Notice, Pill, cardCls } from "@/components/studio/ui";

export default function SetupPage() {
  const t = useT();
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [platforms, setPlatforms] = useState<PlatformReadiness[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await studio.providers();
        setProviders(data.providers);
        setPlatforms(data.platforms);
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-white">{t("su.title")}</h1>
      <Notice>{t("su.secrets")}</Notice>
      <ErrorBox message={error} />
      {providers === null && !error && <Loading />}

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
