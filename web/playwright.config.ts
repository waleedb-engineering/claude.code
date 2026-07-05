import { defineConfig, devices } from "@playwright/test";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// ClipForge — kritische Browser-E2E-Smoke-Suite.
//
// Deterministisch, klein, offline: keine echten Google-/YouTube-Calls, keine
// echten Uploads, keine Tokens. Der Browser wird NICHT heruntergeladen — wir
// nutzen das in dieser Umgebung vorinstallierte Chromium.
// ---------------------------------------------------------------------------

const FRONTEND_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const BACKEND_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

// Vorinstalliertes Chromium auflösen (kein Download). Zuerst der stabile
// Symlink, dann ein Glob über PLAYWRIGHT_BROWSERS_PATH als Fallback.
function resolveChromium(): string | undefined {
  const explicit = process.env.E2E_CHROMIUM_PATH;
  if (explicit && existsSync(explicit)) return explicit;

  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !existsSync(root)) return undefined;

  const symlink = join(root, "chromium");
  if (existsSync(symlink)) return symlink;

  try {
    for (const entry of readdirSync(root)) {
      if (!entry.startsWith("chromium-")) continue;
      const candidate = join(root, entry, "chrome-linux", "chrome");
      if (existsSync(candidate)) return candidate;
    }
  } catch {
    /* nichts gefunden — Playwright-Default greift */
  }
  return undefined;
}

const chromiumPath = resolveChromium();

// Backend-Job-Verzeichnis für E2E isolieren (keine echten Nutzer-Daten). Nur
// relevant, wenn Playwright den Backend-Server selbst startet (CI).
const E2E_JOBS_DIR =
  process.env.CLIPFORGE_JOBS_DIR ?? join(__dirname, ".e2e-jobs");

export default defineConfig({
  testDir: "./e2e",
  // Ein gemeinsames Backend + echte Job-Artefakte → seriell ausführen, damit
  // Datenisolierung/Zählungen deterministisch bleiben.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Echte Jobs (Upload → ffmpeg-Render) brauchen etwas Zeit.
  timeout: 150_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],

  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: chromiumPath ? { executablePath: chromiumPath } : {},
      },
    },
  ],

  // Server nur starten, wenn keine laufen (lokal werden bestehende Dev-Server
  // wiederverwendet; in CI frisch gestartet). Backend zuerst.
  webServer: [
    {
      command: `python3 -m uvicorn app:app --host 127.0.0.1 --port 8000`,
      cwd: join(__dirname, "..", "api"),
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { CLIPFORGE_JOBS_DIR: E2E_JOBS_DIR },
    },
    {
      command: `npm run dev`,
      cwd: __dirname,
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_BASE_URL: BACKEND_URL },
    },
  ],
});
