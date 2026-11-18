"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";
import { resetSession } from "@/lib/session";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setError(data?.detail?.message ?? "Anmeldung fehlgeschlagen.");
        return;
      }
      resetSession();
      const next = new URLSearchParams(window.location.search).get("next");
      // nur interne Ziele (kein Open Redirect)
      window.location.assign(next && next.startsWith("/") && !next.startsWith("//") ? next : "/studio");
    } catch {
      setError("Server nicht erreichbar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto mt-16 max-w-sm space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-6">
      <h1 className="text-xl font-semibold text-white">Anmelden</h1>
      {error && (
        <p role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {error}
        </p>
      )}
      <div>
        <label htmlFor="l-user" className="mb-1 block text-xs font-medium text-neutral-300">
          Benutzername
        </label>
        <input
          id="l-user"
          autoComplete="username"
          required
          className="w-full rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400/40"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="l-pass" className="mb-1 block text-xs font-medium text-neutral-300">
          Passwort
        </label>
        <input
          id="l-pass"
          type="password"
          autoComplete="current-password"
          required
          className="w-full rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400/40"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
      >
        {busy ? "Anmelden …" : "Anmelden"}
      </button>
    </form>
  );
}
