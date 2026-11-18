// Local-API-Session: Das Backend verlangt für alle mutierenden Requests den
// Header X-ClipForge-Token. Das Token gibt es nur für die lokale Oberfläche
// unter GET /api/session; es wird im Speicher gehalten (nie in localStorage).

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL === "same-origin"
    ? ""
    : process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
export const TOKEN_HEADER = "X-ClipForge-Token";

let cached: Promise<string | null> | null = null;

async function load(): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/api/session`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as { token: string | null };
    return data.token ?? null;
  } catch {
    return null;
  }
}

export function getToken(refresh = false): Promise<string | null> {
  if (!cached || refresh) cached = load();
  return cached;
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

/** fetch-Ersatz: hängt bei Mutationen das Token an und versucht es bei
 *  401/403 (z. B. Backend-Neustart mit neuem Token) genau einmal erneut. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
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
  if (code !== "token_missing" && code !== "token_invalid") return res;
  return send(true);
}
