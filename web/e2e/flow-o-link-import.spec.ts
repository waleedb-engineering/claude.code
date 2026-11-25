import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_API_TOKEN } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow O — Link-Import: standardmäßig aus, Einschalten nur mit Hinweis-Bestätigung,
// Rechte-Bestätigung je Link, ungültige Links werden verständlich abgelehnt.
// Kein echter Download (diese Umgebung lädt bewusst nichts von YouTube/Twitch).
// ---------------------------------------------------------------------------

const H = { "Content-Type": "application/json", "X-ClipForge-Token": E2E_API_TOKEN };

test("Link-Import: einschalten, Rechte bestätigen, ungültigen Link ablehnen", async ({ page, errors }) => {
  errors.allow(/Failed to load resource.*400/); // der ungültige Link wird bewusst mit 400 abgelehnt
  await fetch(`${API_URL}/api/studio/stream-link-import`, { method: "PUT", headers: H, body: JSON.stringify({ enabled: false }) });
  try {
    await page.goto("/studio/streams");
    const card = page.getByRole("region", { name: "Aus Link clippen (YouTube / Twitch)" });
    await expect(card.getByText(/Nutzungsbedingungen/)).toBeVisible();
    const enable = card.getByRole("button", { name: "Link-Import einschalten" });
    await expect(enable).toBeDisabled();
    await card.getByLabel(/Verstanden/).check();
    await enable.click();
    const url = card.getByLabel("Link zum Video oder zur vergangenen Übertragung");
    await expect(url).toBeVisible();
    const go = card.getByRole("button", { name: "Laden und Highlights finden" });
    await url.fill("https://www.youtube.com/playlist?list=PL0123456789");
    await expect(go).toBeDisabled(); // Rechte noch nicht bestätigt
    await card.getByLabel(/mein eigener Inhalt/).check();
    await go.click();
    await expect(card.getByText(/Wiedergabelisten und Kanäle werden nicht unterstützt/)).toBeVisible();
    await card.getByRole("button", { name: "Link-Import ausschalten" }).click();
    await expect(card.getByRole("button", { name: "Link-Import einschalten" })).toBeVisible();
  } finally {
    await fetch(`${API_URL}/api/studio/stream-link-import`, { method: "PUT", headers: H, body: JSON.stringify({ enabled: false }) });
  }
});
