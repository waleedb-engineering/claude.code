import { test, expect } from "./helpers/fixtures";
import {
  installYouTubeMocks,
  expectNoSecretsInDom,
  dryRunDisabled,
  reauthStatus,
  readinessWithTokenStore,
  oauthStatusReady,
  oauthStartUrl,
} from "./helpers/youtube";

// ---------------------------------------------------------------------------
// Flow G — Reauth-UI (gemockte /youtube/*-Endpoints).
//
// requires_reauth=true → „YouTube erneut verbinden“ sichtbar, kein Token im DOM,
// kein automatischer Browser-Login (kein Popup), Consent-URL nur manuell, und
// Logout funktioniert weiterhin.
// ---------------------------------------------------------------------------

test("Reauth: erneut verbinden, kein Token im DOM, kein Auto-Login, Logout funktioniert", async ({
  page,
  seeded,
}) => {
  await installYouTubeMocks(page, {
    dryRun: dryRunDisabled(),
    uploadStatus: reauthStatus(),
    readiness: readinessWithTokenStore(),
    oauthStatus: oauthStatusReady(),
    oauthStart: oauthStartUrl(),
    logout: { deleted: true },
  });

  await page.goto(`/jobs/${seeded.job.jobId}/publishing`);
  const card = page.locator(`#draft-${seeded.publishingId}`);

  // Upload-Bereitschaft prüfen → Reauth-Hinweis.
  await card.getByRole("button", { name: "Upload-Bereitschaft prüfen" }).click();
  await expect(card.getByText(/erneut verbunden werden/)).toBeVisible();
  const reconnect = card.getByRole("button", { name: "YouTube erneut verbinden" });
  await expect(reconnect).toBeVisible();

  // Kein Upload-Button im Reauth-Zustand.
  await expect(card.getByRole("button", { name: /hochladen/i })).toHaveCount(0);

  // Verbinden vorbereiten → nur manuelle Consent-URL, kein Popup/Auto-Login.
  await reconnect.click();
  await expect(page.getByText(/kein Browser automatisch geöffnet/)).toBeVisible();
  expect(page.context().pages().length).toBe(1);
  await expectNoSecretsInDom(page);

  // Logout funktioniert weiterhin (Readiness-Panel). Der Erfolgstext wird durch
  // das direkt folgende Readiness-Reload wieder geleert, daher die Antwort des
  // Logout-Endpoints selbst verifizieren (deleted:true).
  await card.getByRole("button", { name: "YouTube-Readiness prüfen" }).click();
  const logoutBtn = card.getByRole("button", { name: "YouTube-Token löschen" });
  await expect(logoutBtn).toBeVisible();
  const [logoutResp] = await Promise.all([
    page.waitForResponse("**/youtube/auth/logout"),
    logoutBtn.click(),
  ]);
  expect(logoutResp.ok()).toBe(true);
  expect((await logoutResp.json()).deleted).toBe(true);

  await expectNoSecretsInDom(page);
});
