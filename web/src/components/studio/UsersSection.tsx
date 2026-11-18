"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { apiFetch, resetSession, sessionInfo, type SessionInfo } from "@/lib/session";
import { ErrorBox, btnCls, cardCls, inputCls, labelCls, primaryCls } from "./ui";

type User = { username: string; role: string; created_at: string };
type Sess = { id: string; created: number; expires: number; current: boolean };

async function call(path: string, method = "GET", body?: unknown) {
  const res = await apiFetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail?.message ?? `HTTP ${res.status}`);
  return data;
}

/** Konto, Passwort, Sitzungen; für Admins: Benutzerverwaltung. Nur im Online-Betrieb. */
export default function UsersSection() {
  const t = useT();
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pw, setPw] = useState({ old: "", next: "" });
  const [nu, setNu] = useState({ username: "", password: "", role: "user" });

  const load = useCallback(async () => {
    const i = await sessionInfo();
    setInfo(i);
    if (i.mode !== "accounts" || !i.user) return;
    try {
      setSessions((await call("/api/auth/sessions")).sessions);
      if (i.role === "admin") setUsers((await call("/api/admin/users")).users);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  if (!info || info.mode !== "accounts" || !info.user) return null;

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null);
    setNote(null);
    try {
      await fn();
      setNote(ok);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section id="account" aria-labelledby="us-h" className={`${cardCls} space-y-4`}>
      <h2 id="us-h" className="text-lg font-semibold text-white">
        {t("us.title")}
      </h2>
      <p className="text-sm text-neutral-300">
        {info.user} · {info.role === "admin" ? "Admin" : t("us.roleUser")} ·{" "}
        {info.workspaces === "shared" ? t("us.shared") : t("us.ownSpace")}
      </p>
      {info.must_change_password && <p className="text-sm text-amber-300">{t("us.mustChange")}</p>}
      <ErrorBox message={error} />
      {note && (
        <p role="status" className="text-sm text-emerald-300">
          {note}
        </p>
      )}

      <form
        className="grid gap-2 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await call("/api/auth/password", "POST", { old_password: pw.old, new_password: pw.next });
            resetSession();
            window.location.assign("/login");
          }, t("us.changed"));
        }}
      >
        <div>
          <label htmlFor="us-old" className={labelCls}>
            {t("us.oldPw")}
          </label>
          <input id="us-old" type="password" autoComplete="current-password" className={inputCls} value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} />
        </div>
        <div>
          <label htmlFor="us-new" className={labelCls}>
            {t("us.newPw")}
          </label>
          <input id="us-new" type="password" autoComplete="new-password" minLength={12} className={inputCls} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
        </div>
        <div className="flex items-end">
          <button type="submit" className={btnCls} disabled={!pw.old || pw.next.length < 12}>
            {t("us.changePw")}
          </button>
        </div>
      </form>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">{t("us.sessions")}</h3>
        <ul className="mt-1 text-xs text-neutral-300">
          {sessions.map((s) => (
            <li key={s.id}>
              {new Date(s.created * 1000).toLocaleString()} → {new Date(s.expires * 1000).toLocaleDateString()}
              {s.current ? ` (${t("us.thisSession")})` : ""}
            </li>
          ))}
        </ul>
        <button type="button" className={`${btnCls} mt-2`} onClick={() => void run(() => call("/api/auth/sessions/revoke-others", "POST"), t("us.revoked"))}>
          {t("us.revokeOthers")}
        </button>
      </div>

      {info.role === "admin" && (
        <div className="space-y-2 border-t border-neutral-800 pt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">{t("us.admin")}</h3>
          <ul className="divide-y divide-neutral-800 text-sm">
            {users.map((u) => (
              <li key={u.username} className="flex flex-wrap items-center justify-between gap-2 py-1">
                <span className="text-neutral-200">
                  {u.username} <span className="text-xs text-neutral-500">({u.role})</span>
                </span>
                {u.username !== info.user && (
                  <span className="flex gap-2">
                    <button
                      type="button"
                      className={btnCls}
                      onClick={() => {
                        const p = window.prompt(t("us.tempPw"));
                        if (p) void run(() => call(`/api/admin/users/${encodeURIComponent(u.username)}/password`, "POST", { password: p }), t("us.resetDone"));
                      }}
                    >
                      {t("us.resetPw")}
                    </button>
                    <button
                      type="button"
                      className={btnCls}
                      onClick={() => {
                        if (window.confirm(t("us.deleteConfirm"))) void run(() => call(`/api/admin/users/${encodeURIComponent(u.username)}`, "DELETE"), t("us.deleted"));
                      }}
                    >
                      {t("common.delete")}
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
          <form
            className="grid gap-2 sm:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                await call("/api/admin/users", "POST", nu);
                setNu({ username: "", password: "", role: "user" });
              }, t("us.created"));
            }}
          >
            <input aria-label={t("us.username")} placeholder={t("us.username")} className={inputCls} value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} />
            <input aria-label={t("us.tempPw")} type="password" placeholder={t("us.tempPw")} minLength={12} className={inputCls} value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} />
            <select aria-label={t("us.role")} className={inputCls} value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>
              <option value="user">{t("us.roleUser")}</option>
              <option value="admin">Admin</option>
            </select>
            <button type="submit" className={primaryCls} disabled={!nu.username || nu.password.length < 12}>
              {t("us.create")}
            </button>
          </form>
        </div>
      )}
    </section>
  );
}
