// Local-API-Session: Das Backend verlangt für alle mutierenden Requests den
// Header X-ClipForge-Token. Das Token gibt es nur für die lokale Oberfläche
// unter GET /api/session; es wird im Speicher gehalten (nie in localStorage).

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL === "same-origin"
    ? ""
    : process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
export const TOKEN_HEADER = "X-ClipForge-Token";

let cached: Promise<string | null> | null = null;

export type SessionInfo = {
  mode: "local" | "accounts";
  user: string | null;
  token: string | null;
  role?: "admin" | "user" | null;
  must_change_password?: boolean;
  workspaces?: "per_user" | "shared";
  registration_open?: boolean;
};

/** Online-Betrieb: ohne Anmeldung zur Login-Seite (außer man ist schon dort). */
export function goToLogin(): void {
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}`);
}

export async function sessionInfo(): Promise<SessionInfo> {
  try {
    const res = await fetch(`${BASE}/api/session`, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) return { mode: "accounts", user: null, token: null };
    return {
      mode: data.mode === "accounts" ? "accounts" : "local",
      user: data.user ?? null,
      token: data.token ?? null,
      role: data.role ?? null,
      must_change_password: !!data.must_change_password,
      workspaces: data.workspaces,
      registration_open: !!data.registration_open,
    };
  } catch {
    return { mode: "local", user: null, token: null };
  }
}

async function load(): Promise<string | null> {
  const info = await sessionInfo();
  if (info.mode === "accounts" && !info.user) goToLogin();
  return info.token;
}

export function resetSession(): void {
  cached = null;
}

export function getToken(refresh = false): Promise<string | null> {
  if (!cached || refresh) cached = load();
  return cached;
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

/** fetch-Ersatz: hängt bei Mutationen das Token an und versucht es bei
 *  401/403 (z. B. Backend-Neustart mit neuem Token) genau einmal erneut. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const res = await apiFetchInner(input, init);
  if (res.status === 401) {
    const code = (await res.clone().json().catch(() => null))?.detail?.code;
    if (code === "login_required") goToLogin();
  }
  return res;
}

async function apiFetchInner(input: string, init: RequestInit): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  if (SAFE.has(method)) return fetch(input, init);
  const send = async (refresh: boolean) => {
    const token = await getToken(refresh);
    const headers = new Headers(init.headers);
    if (token) headers.set(TOKEN_HEADER, token);
    return fetch(input, { ...init, headers });
  };
  const res = await send(false);
  if (res.status !== 401 && res.status !== 403) return res;
  const body = await res.clone().json().catch(() => null);
  const code = body?.detail?.code;
  if (code !== "token_missing" && code !== "token_invalid" && code !== "csrf_invalid") return res;
  return send(true);
}
