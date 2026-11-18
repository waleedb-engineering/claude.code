// Serverseitiger Durchleitungsweg Oberfläche → FastAPI-Backend.
//
// Wozu: Läuft ClipForge auf einem Rechner, den der Browser nur über EINEN Port
// erreicht (z. B. Vorschau-Link einer Cloud-Sitzung), kann die Oberfläche das
// Backend auf :8000 nicht direkt ansprechen. Mit NEXT_PUBLIC_API_BASE_URL=
// "same-origin" schickt sie alle API-Aufrufe an /api/* der eigenen Herkunft,
// und dieser Handler leitet sie an das Backend weiter.
//
// Sicherheit (unverändert durch den Proxy):
//   - Das Backend verlangt weiterhin für JEDE Mutation das Session-Token.
//   - Fremde Herkunft wird hier abgewiesen: Ein mutierender Request muss einen
//     Origin haben, der zum eigenen Host passt.
//   - Host-Allowlist gegen DNS-Rebinding: lokal (localhost/127.0.0.1) plus
//     CLIPFORGE_PUBLIC_HOSTS; CLIPFORGE_PROXY_ANY_HOST=1 nur für Umgebungen,
//     die ausschließlich über einen vertrauenswürdigen, authentifizierten
//     Proxy erreichbar sind (Cloud-Vorschau).

const BACKEND = (process.env.CLIPFORGE_API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);
const LOCAL = new Set(["localhost", "127.0.0.1", "[::1]"]);
const DROP_REQUEST = new Set(["host", "origin", "referer", "connection", "content-length", "cookie"]);
const DROP_RESPONSE = new Set(["content-encoding", "content-length", "transfer-encoding", "connection"]);

function hostOf(value: string | null): string {
  return (value ?? "").split(",")[0].trim().toLowerCase();
}

function hostAllowed(host: string): boolean {
  if (process.env.CLIPFORGE_PROXY_ANY_HOST === "1") return true;
  const name = host.replace(/:\d+$/, "");
  const extra = (process.env.CLIPFORGE_PUBLIC_HOSTS ?? "")
    .split(",")
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean);
  return LOCAL.has(name) || extra.includes(host) || extra.includes(name);
}

function deny(status: number, code: string, message: string): Response {
  return Response.json({ detail: { code, message } }, { status });
}

export async function proxy(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const host = hostOf(request.headers.get("x-forwarded-host")) || hostOf(request.headers.get("host"));
  if (!hostAllowed(host)) {
    return deny(403, "host_not_allowed", "Dieser Host darf die ClipForge-API nicht verwenden.");
  }
  const method = request.method.toUpperCase();
  const origin = request.headers.get("origin");
  if (!SAFE.has(method) || url.pathname === "/api/session") {
    if (origin && origin !== "null") {
      let originHost = "";
      try {
        originHost = new URL(origin).host.toLowerCase();
      } catch {
        originHost = "";
      }
      if (originHost !== host) {
        return deny(403, "origin_not_allowed", "Diese Herkunft darf die ClipForge-API nicht verwenden.");
      }
    }
  }
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!DROP_REQUEST.has(key.toLowerCase()) && !key.toLowerCase().startsWith("x-forwarded")) {
      headers.set(key, value);
    }
  });
  const init: RequestInit & { duplex?: "half" } = { method, headers, redirect: "manual" };
  if (!SAFE.has(method) && request.body) {
    init.body = request.body;
    init.duplex = "half"; // Uploads streamen statt puffern
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}${url.pathname}${url.search}`, init);
  } catch {
    return deny(502, "backend_unreachable", "Das ClipForge-Backend ist nicht erreichbar.");
  }
  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROP_RESPONSE.has(key.toLowerCase())) out.set(key, value);
  });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}
