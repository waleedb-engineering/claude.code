"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { apiFetch, resetSession, sessionInfo } from "@/lib/session";

/** Zeigt im Online-Betrieb den angemeldeten Benutzer und „Abmelden“. Lokal: nichts. */
export default function AccountMenu() {
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    sessionInfo().then((info) => {
      if (alive && info.mode === "accounts") setUser(info.user);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (!user) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-neutral-300">
      <span>{user}</span>
      <button
        type="button"
        className="rounded-lg border border-neutral-700 px-2 py-1 hover:border-neutral-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        onClick={async () => {
          await apiFetch(`${API_BASE}/api/auth/logout`, { method: "POST" });
          resetSession();
          window.location.assign("/login");
        }}
      >
        Abmelden
      </button>
    </div>
  );
}
