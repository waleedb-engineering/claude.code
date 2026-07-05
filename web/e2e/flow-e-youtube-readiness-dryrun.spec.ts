import { test, expect } from "./helpers/fixtures";
import { expectNoSecretsInDom } from "./helpers/youtube";

// ---------------------------------------------------------------------------
// Flow E — YouTube Readiness + Dry-Run (echtes Backend, keine Credentials).
//
// Nutzt bewusst die ECHTEN /youtube/readiness- & /dry-run-Endpoints (ohne
// konfigurierte Credentials → alles blockiert, nie ein Google-Call). Prüft die
// Sicherheitszusagen: kein Public/Unlisted-Button, keine Secrets im DOM.
// ---------------------------------------------------------------------------

test("YouTube Dry-Run & Readiness: sicher, ohne Secrets, ohne Public/Unlisted", async ({
  page,
  seeded,
}) => {
  await page.goto(`/jobs/${seeded.job.jobId}/publishing`);
  const card = page.locator(`#draft-${seeded.publishingId}`);
  await expect(card).toBeVisible();

  // Dry-Run: Feature ist deaktiviert → „Dry-Run only“.
  await card.getByRole("button", { name: "YouTube Dry-Run prüfen" }).click();
  await expect(card.getByText(/Dry-Run only/)).toBeVisible();
  await expect(card.getByText(/garantiert nichts hochgeladen/)).toBeVisible();

  // Readiness: sagt nur, ob Upload später möglich WÄRE — implementiert/aktiv ist er nicht.
  await card.getByRole("button", { name: "YouTube-Readiness prüfen" }).click();
  await expect(card.getByText("Token vorhanden")).toBeVisible(); // Readiness-Checkliste gerendert
  await expect(card.getByText(/nicht implementiert/).first()).toBeVisible();

  // Es gibt NIRGENDS einen Public-/Unlisted-/Öffentlich-Schalter.
  await expect(
    page.getByRole("button", { name: /public|unlisted|öffentlich/i }),
  ).toHaveCount(0);
  await expect(page.getByText(/\bunlisted\b/i)).toHaveCount(0);

  // Keine Tokens/Secrets im DOM.
  await expectNoSecretsInDom(page);
});
