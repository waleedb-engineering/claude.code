import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_PREFIX, deleteJob } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow I — Creator Studio (Skript → Editor → Render → Publishing-Übergabe).
//
// Läuft komplett lokal: kein Netz, keine Provider, keine Kosten. Der Render
// ist ein echter FFmpeg-Lauf (stumm, da in der Testumgebung kein lokaler
// Sprach-Provider vorhanden ist).
// ---------------------------------------------------------------------------

const SCRIPT =
  "Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner. " +
  "Jede Szene bleibt bearbeitbar. Folge für mehr.";

async function cleanupProject(projectId: string) {
  const view = await fetch(`${API_URL}/api/studio/projects/${projectId}`).then((r) => (r.ok ? r.json() : null));
  for (const exp of view?.project?.exports ?? []) await deleteJob(exp.job_id);
  await fetch(`${API_URL}/api/studio/projects/${projectId}`, { method: "DELETE" });
}

test("Studio: Skript → Editor (Autosave, Undo, Reihenfolge) → Render → Publishing", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/studio");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();
  await page.getByRole("link", { name: "+ Neues Video" }).click();

  await page.getByRole("radio", { name: "Skript → Video" }).check();
  await page.getByLabel("Titel (optional)").fill(`${E2E_PREFIX} Studio`);
  await page.getByLabel("Skript", { exact: true }).fill(SCRIPT);
  await page.getByLabel("Auflösung").selectOption("720p");
  await page.getByRole("button", { name: "Projekt anlegen" }).click();

  await page.waitForURL(/\/studio\/projects\/[a-f0-9]{12}$/, { timeout: 60_000 });
  const projectId = page.url().split("/").pop() as string;
  try {
    const texts = page.getByLabel("Text (Caption)");
    await expect(texts.first()).toHaveValue(/Lokale Videotools/);
    const count = await texts.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // Text bearbeiten → Autosave → nach Reload vom Backend zurück
    await texts.first().fill("Neuer Hook aus dem E2E-Test.");
    await expect(page.getByText(/✓ Gespeichert/)).toBeVisible({ timeout: 15_000 });
    await page.reload();
    await expect(page.getByLabel("Text (Caption)").first()).toHaveValue("Neuer Hook aus dem E2E-Test.");

    // Reihenfolge ändern (Tastatur-bedienbarer Button) und rückgängig machen
    const second = await page.getByLabel("Text (Caption)").nth(1).inputValue();
    await page.getByRole("button", { name: "Nach unten (1)" }).click();
    await expect(page.getByLabel("Text (Caption)").first()).toHaveValue(second);
    await page.getByRole("button", { name: "↶ Rückgängig" }).click();
    await expect(page.getByLabel("Text (Caption)").first()).toHaveValue("Neuer Hook aus dem E2E-Test.");
    await page.getByRole("button", { name: "↷ Wiederholen" }).click();
    await expect(page.getByLabel("Text (Caption)").first()).toHaveValue(second);

    // Szene duplizieren + löschen wirkt auf die Anzahl
    await page.getByRole("button", { name: "Duplizieren" }).first().click();
    await expect(page.getByLabel("Text (Caption)")).toHaveCount(count + 1);
    await page.getByRole("button", { name: "Löschen (1)" }).click();
    await expect(page.getByLabel("Text (Caption)")).toHaveCount(count);

    // Caption-Stil ändern → Vorschau-Bild lädt
    await page.locator("#s-cap").selectOption("bold");
    await expect(page.getByAltText("Caption-Vorschau: bold")).toBeVisible();
    await expect(page.getByText(/✓ Gespeichert/)).toBeVisible({ timeout: 15_000 });

    // Vorschau + finaler Render (echtes FFmpeg)
    await page.getByRole("button", { name: "Vorschau rendern" }).click();
    await expect(page.locator("video").first()).toBeVisible({ timeout: 120_000 });
    await page.getByRole("button", { name: "Final rendern" }).click();
    await expect(page.getByText(/FINAL · 720×1280/i)).toBeVisible({ timeout: 150_000 });

    // Backend bestätigt: Reihenfolge + Stil gespeichert, Render vorhanden
    const view = await (await fetch(`${API_URL}/api/studio/projects/${projectId}`)).json();
    expect(view.project.captions.style).toBe("bold");
    expect(view.project.scenes[0].text).toBe(second);
    expect(view.renders.some((r: { mode: string }) => r.mode === "final")).toBe(true);

    // Übergabe an den Publishing-Planner (nichts wird veröffentlicht)
    await page.getByRole("button", { name: "An Publishing übergeben" }).click();
    await page.waitForURL(/\/jobs\/[a-f0-9]{12}\/publishing$/, { timeout: 30_000 });
    const drafts = await (await fetch(`${API_URL}/api/studio/publishing/drafts`)).json();
    expect(drafts.drafts.every((d: { published_at: string | null }) => d.published_at === null)).toBe(true);
  } finally {
    // Seite verlassen, bevor aufgeräumt wird — sonst pollt sie gelöschte Daten (404).
    await page.goto("/studio/setup");
    await page.getByRole("heading", { name: "Einrichtung & Bereitschaft" }).waitFor();
    await cleanupProject(projectId);
  }
});

test("Studio: nicht verfügbare Workflows sind deaktiviert und begründet", async ({ page }) => {
  await page.goto("/studio/create");
  await expect(page.getByRole("radio", { name: "YouTube → Shorts" })).toBeEnabled();
  await expect(page.getByRole("radio", { name: "Talking Avatar" })).toBeDisabled();
  await expect(page.getByText(/Talking Avatar ist nicht verfügbar/)).toBeVisible();
  await expect(page.getByRole("radio", { name: "PDF → Video" })).toBeEnabled();
});

test("Studio: URL auf lokale Adresse wird verständlich abgelehnt", async ({ page, errors }) => {
  errors.allow(/Failed to load resource.*400/);
  await page.goto("/studio/create");
  await page.getByRole("radio", { name: "Artikel/Blog → Video" }).check();
  await page.getByLabel("URL (öffentlich erreichbar)").fill("http://127.0.0.1:8000/health");
  await page.getByRole("button", { name: "Projekt anlegen" }).click();
  await expect(page.getByText(/nicht erlaubt/)).toBeVisible();
  await expect(page).toHaveURL(/\/studio\/create$/);
});

test("Studio: Einrichtung zeigt Readiness ohne Secrets, Sprache umschaltbar", async ({ page }) => {
  await page.goto("/studio/setup");
  await expect(page.getByRole("heading", { name: "Einrichtung & Bereitschaft" })).toBeVisible();
  await expect(page.getByLabel("Provider").getByText("ElevenLabs (Cloud)")).toBeVisible();
  await expect(page.getByText("ELEVENLABS_API_KEY", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Nicht konfiguriert").first()).toBeVisible();
  await expect(page.getByText("Nicht verbunden").first()).toBeVisible();

  await page.getByRole("button", { name: "en", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Setup & readiness" })).toBeVisible();
  await expect(page.getByText("Not connected").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Automations" })).toBeVisible();
  await page.getByRole("button", { name: "de", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Einrichtung & Bereitschaft" })).toBeVisible();
});

test("Studio: Idee speichern, filtern, Automation anlegen und pausieren", async ({ page }) => {
  const title = `${E2E_PREFIX} Idee ${Date.now()}`;
  await page.goto("/studio/ideas");
  await expect(page.getByText(/Inspiration, keine Kopie/)).toBeVisible();
  await page.getByLabel("Titel", { exact: true }).fill(title);
  await page.getByLabel("Nische").first().fill("kaffee");
  await page.getByRole("button", { name: "Idee speichern" }).click();
  await expect(page.getByText(title)).toBeVisible();
  await page.getByLabel("Suchen …").fill("gibt-es-nicht-xyz");
  await expect(page.getByText(title)).toHaveCount(0);
  await page.getByLabel("Suchen …").fill(title);
  await expect(page.getByText(title)).toBeVisible();
  await page.getByRole("button", { name: `Löschen: ${title}` }).click();
  await expect(page.getByText(title)).toHaveCount(0);

  const name = `${E2E_PREFIX} Auto ${Date.now()}`;
  await page.goto("/studio/automations");
  await expect(page.getByText(/Sie veröffentlichen nie/)).toBeVisible();
  await page.getByRole("button", { name: "+ Neue Automation" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel(/Themen\/Skripte\/URLs/).fill("Erstes Thema\nZweites Thema");
  await page.getByRole("button", { name: "Automation anlegen" }).click();
  const card = page.getByRole("listitem").filter({ hasText: name });
  await expect(card.getByText(/Nächster Lauf:/)).toBeVisible();
  await card.getByRole("button", { name: "Pausieren" }).click();
  await expect(card.getByText("Pausiert")).toBeVisible();
  await card.getByRole("button", { name: "Fortsetzen" }).click();
  await expect(card.getByText(/Nächster Lauf:/)).toBeVisible();
  await card.getByRole("button", { name: "Löschen" }).click();
  await expect(page.getByText(name)).toHaveCount(0);
});

test("Studio: API-Schlüssel setzen wirkt sofort, Wert erscheint nie, Entfernen ebenso", async ({ page }) => {
  const secret = "sentinel-e2e-elevenlabs-key";
  await page.goto("/studio/setup");
  const card = page.getByRole("listitem").filter({ hasText: "ELEVENLABS_API_KEY" }).first();
  await expect(card.getByText("Nicht hinterlegt")).toBeVisible();
  await card.getByLabel(/Schlüssel/).fill(secret);
  await card.getByRole("button", { name: "Speichern" }).click();
  await expect(card.getByText("Hinterlegt", { exact: true }).first()).toBeVisible();
  // Provider ist ohne Neustart einsatzbereit
  const providers = await (await fetch(`${API_URL}/api/studio/providers`)).json();
  const eleven = providers.providers.find((p: { id: string }) => p.id === "elevenlabs");
  expect(eleven.status).toBe("ready");
  expect(JSON.stringify(providers)).not.toContain(secret);
  expect(await page.content()).not.toContain(secret);
  await card.getByRole("button", { name: "Entfernen" }).click();
  await expect(card.getByText("Nicht hinterlegt").first()).toBeVisible();
  const after = await (await fetch(`${API_URL}/api/studio/providers`)).json();
  expect(after.providers.find((p: { id: string }) => p.id === "elevenlabs").status).toBe("not_configured");
});

test("Local API: Mutation ohne Token und von fremder Herkunft wird abgewiesen", async ({ request }) => {
  const body = { workflow: "script", script: "Erster Satz hier. Zweiter Satz hier." };
  const noToken = await request.post(`${API_URL}/api/studio/projects`, { data: body });
  expect(noToken.status()).toBe(401);
  const foreign = await request.post(`${API_URL}/api/studio/projects`, {
    data: body,
    headers: { Origin: "https://evil.example", "X-ClipForge-Token": "e2e-local-token-0123456789abcdef" },
  });
  expect(foreign.status()).toBe(403);
  const session = await request.get(`${API_URL}/api/session`, { headers: { Origin: "https://evil.example" } });
  expect(session.status()).toBe(403);
});
