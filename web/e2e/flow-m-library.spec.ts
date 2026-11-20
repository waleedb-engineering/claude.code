import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_API_TOKEN, E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow M — Mediathek: Hauptnavigation, Upload mit Tags, Duplikat-Hinweis,
// Suche, Details, in Projekt verwenden, Löschen mit Bestätigung.
// ---------------------------------------------------------------------------

const H = { "Content-Type": "application/json", "X-ClipForge-Token": E2E_API_TOKEN };

test("Mediathek: hochladen, Duplikat, suchen, verwenden, löschen", async ({ page }) => {
  test.setTimeout(120_000);
  const dir = mkdtempSync(join(tmpdir(), "cf-lib-"));
  const png = join(dir, "e2e-logo.png");
  execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", `color=c=0x${Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0")}:s=64x64:d=1`, "-frames:v", "1", png]);
  const created = await fetch(`${API_URL}/api/studio/projects`, {
    method: "POST",
    headers: H,
    body: JSON.stringify({ workflow: "script", title: `${E2E_PREFIX} Lib`, script: "Erster Satz hier. Zweiter Satz dort. Folge für mehr." }),
  }).then((r) => r.json());
  const pid = created.project.id as string;
  // Reste früherer Läufe entfernen
  const old = await fetch(`${API_URL}/api/studio/library?q=e2e-logo`).then((r) => r.json());
  for (const it of old.items ?? []) await fetch(`${API_URL}/api/studio/library/${it.id}?force=true`, { method: "DELETE", headers: H });
  try {
    await page.goto("/studio");
    await page.getByRole("navigation", { name: "Hauptnavigation" }).getByRole("link", { name: "Mediathek" }).click();
    await expect(page.getByRole("heading", { name: "Mediathek" })).toBeVisible();
    await page.getByLabel("Tags (Komma)").fill("e2e, logo");
    await page.getByLabel("Dateien").setInputFiles(png);
    const grid = page.getByTestId("library-grid");
    await expect(grid.getByText("e2e-logo.png")).toBeVisible();
    await page.getByLabel("Dateien").setInputFiles(png);
    await expect(page.getByText(/schon in der Mediathek/)).toBeVisible();
    await page.getByLabel("Suche").fill("e2e-logo");
    await expect(grid.locator("li")).toHaveCount(1);
    await page.getByRole("button", { name: "Details e2e-logo.png" }).click();
    await page.getByLabel("In Projekt verwenden").selectOption(pid);
    await page.getByRole("button", { name: "Verwenden" }).click();
    await expect(page.getByText(/In das Projekt kopiert/)).toBeVisible();
    const media = await fetch(`${API_URL}/api/studio/projects/${pid}/media`).then((r) => r.json());
    expect(media.media.some((m: { name: string }) => m.name.startsWith("e2e-logo"))).toBe(true);
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Löschen" }).click();
    await expect(grid.locator("li")).toHaveCount(0);
  } finally {
    await fetch(`${API_URL}/api/studio/projects/${pid}`, { method: "DELETE", headers: H });
  }
});
