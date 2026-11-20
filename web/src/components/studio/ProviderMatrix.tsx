"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { studio } from "@/lib/studio";
import { Pill, cardCls } from "./ui";

/** Alle Anbieter auf einen Blick: Status, Kosten, Limits, Fallback, Live-Verifizierung. */
export default function ProviderMatrix() {
  const t = useT();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof studio.providerMatrix>>>([]);
  useEffect(() => {
    const first = setTimeout(async () => {
      try {
        setRows(await studio.providerMatrix());
      } catch {
        /* optional */
      }
    }, 0);
    return () => clearTimeout(first);
  }, []);
  if (!rows.length) return null;
  return (
    <section aria-labelledby="pm-h" className={`${cardCls} space-y-2`}>
      <h2 id="pm-h" className="text-lg font-semibold text-white">
        {t("pm.title")}
      </h2>
      <p className="text-xs text-neutral-400">{t("pm.hint")}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-neutral-300">
          <thead className="text-neutral-400">
            <tr>
              <th className="py-1 pr-3">{t("pm.provider")}</th>
              <th className="pr-3">{t("pm.category")}</th>
              <th className="pr-3">Status</th>
              <th className="pr-3">{t("pm.cost")}</th>
              <th className="pr-3">{t("pm.limits")}</th>
              <th className="pr-3">Fallback</th>
              <th>{t("pm.verified")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-neutral-800">
                <td className="py-1 pr-3 text-neutral-100">{r.label}</td>
                <td className="pr-3">{r.category}</td>
                <td className="pr-3">
                  <Pill status={r.status} />
                </td>
                <td className="pr-3">{r.paid ? `💲 ${r.cost}` : r.cost}</td>
                <td className="pr-3">{r.limits}</td>
                <td className="pr-3">{r.fallback}</td>
                <td>{r.live_verified ? "✓" : t("pm.notVerified")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
