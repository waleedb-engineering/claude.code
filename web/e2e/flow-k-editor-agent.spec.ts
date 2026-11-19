import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_API_TOKEN, E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow K — KI-Assistent im Editor (regelbasiert, lokal, kostenlos):
// Befehl → Plan sichtbar → Ausführen → Editor zeigt Änderung → Rückgängig.
// ---------------------------------------------------------------------------

const H = { "Content-Type": "application/json", "X-ClipForge-Token": E2E_API_TOKEN };

test("Editor-Agent: Szene verschieben per Chat und rückgängig machen", async ({ page }) => {
  test.setTimeout(120_000);
  const created = await fetch(`${API_URL}/api/studio/projects`, {
    method: "POST",
    headers: H,
    body: JSON.stringify({
      workflow: "script",
      title: `${E2E_PREFIX} Agent`,
      script:
        "Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner. " +
        "Jede Szene bleibt bearbeitbar. Folge für mehr.",
    }),
  }).then((r) => r.json());
  const pid = created.project.id as string;
  try {
    for (let i = 0; i < 60; i += 1) {
      const v = await fetch(`${API_URL}/api/studio/projects/${pid}`).then((r) => r.json());
      if (v.project.status === "ready") break;
      await new Promise((r) => setTimeout(r, 500));
    }
    await page.goto(`/studio/projects/${pid}`);
    const texts = page.getByLabel("Text (Caption)");
    const first = await texts.first().inputValue();
    const count = await texts.count();
    expect(count).toBeGreaterThanOrEqual(2);
    await page.getByLabel("Was soll ich ändern?").fill(`Setze Szene ${count} an den Anfang`);
    await page.getByRole("button", { name: "Planen" }).click();
    await expect(page.getByText("move_scene")).toBeVisible();
    await page.getByRole("button", { name: "Ausführen" }).click();
    await expect(page.getByText(/✓ Szene \d+ an Position 1/)).toBeVisible();
    await expect(texts.first()).not.toHaveValue(first);
    await page.getByRole("button", { name: /Letzte KI-Änderung rückgängig/ }).click();
    await expect(texts.first()).toHaveValue(first);
  } finally {
    await fetch(`${API_URL}/api/studio/projects/${pid}`, { method: "DELETE", headers: H });
  }
});
