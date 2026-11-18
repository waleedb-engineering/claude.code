"use client";

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio } from "@/lib/studio";
import { ErrorBox, Notice, Pill, btnCls, cardCls } from "./ui";

type Account = { platform: string; label: string; state: string; account: string | null; requires_env: string[] };

export default function AccountsSection() {
  const t = useT();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [unsupported, setUnsupported] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await studio.accounts();
      setAccounts(data.accounts);
      setUnsupported(data.not_supported);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    const params = new URLSearchParams(window.location.search);
    const result = params.get("result");
    const note = setTimeout(() => {
      if (result && result !== "ok") setError(`${params.get("account")}: ${result}`);
    }, 0);
    return () => {
      clearTimeout(first);
      clearTimeout(note);
    };
  }, [load]);

  return (
    <section aria-labelledby="ac-h" className="space-y-3">
      <h2 id="ac-h" className="text-lg font-semibold text-white">
        {t("ac.title")}
      </h2>
      <ErrorBox message={error} />
      {info && <Notice>{info}</Notice>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {accounts.map((a) => (
          <li key={a.platform} className={cardCls}>
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium text-white">{a.label}</p>
              <div className="flex gap-1">
                <span className="rounded-full border border-amber-500/40 px-2 py-0.5 text-[11px] text-amber-300">
                  {t("su.untested")}
                </span>
                <Pill status={a.state} />
              </div>
            </div>
            {a.account && (
              <p className="mt-1 text-xs text-neutral-300">
                {t("ac.connectedAs")} {a.account}
              </p>
            )}
            {a.state === "not_configured" && (
              <p className="mt-2 text-xs text-neutral-300">
                {t("su.needs")}: <code>{a.requires_env.join(", ")}</code>
              </p>
            )}
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                className={btnCls}
                disabled={a.state === "not_configured"}
                onClick={async () => {
                  try {
                    const { auth_url } = await studio.connectAccount(a.platform);
                    window.open(auth_url, "_blank", "noopener");
                    setInfo(t("ac.opened"));
                  } catch (e) {
                    setError(errorMessage(e));
                  }
                }}
              >
                {t("ac.connect")}
              </button>
              {a.state === "connected" && (
                <button
                  type="button"
                  className={btnCls}
                  onClick={async () => {
                    try {
                      await studio.disconnectAccount(a.platform);
                      await load();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                >
                  {t("ac.disconnect")}
                </button>
              )}
            </div>
          </li>
        ))}
        {Object.entries(unsupported).map(([platform, reason]) => (
          <li key={platform} className={cardCls}>
            <p className="font-medium text-white">{platform}</p>
            <p className="mt-1 text-xs text-neutral-300">
              {t("ac.notSupported")}: {reason}
            </p>
            <p className="mt-1 text-xs text-neutral-400">{t("su.fallback")}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
