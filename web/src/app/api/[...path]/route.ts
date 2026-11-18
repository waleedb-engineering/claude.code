import { proxy } from "@/lib/apiProxy";

// Immer dynamisch: jeder Request geht live ans Backend (kein Caching).
export const dynamic = "force-dynamic";

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
