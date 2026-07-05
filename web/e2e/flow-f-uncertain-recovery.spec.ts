import { test, expect } from "./helpers/fixtures";
import {
  installYouTubeMocks,
  expectNoSecretsInDom,
  dryRunDisabled,
  uncertainStatus,
  reconcilingStatus,
  publishedStatus,
} from "./helpers/youtube";

// ---------------------------------------------------------------------------
// Flow F — Unsicherer Zustand & Recovery-UI (gemockte /youtube/*-Endpoints).
//
// Der „uncertain“-Zustand lässt sich ohne echten Upload nur mocken. Geprüft
// wird: Warntext sichtbar, KEIN Retry/Upload-Button, „Upload-Status prüfen“
// vorhanden, und die Reconciliation uncertain → reconciling → published.
// ---------------------------------------------------------------------------

test("Uncertain-Zustand zeigt Warnung, keinen Retry, und erlaubt Reconciliation", async ({
  page,
  seeded,
}) => {
  await installYouTubeMocks(page, {
    dryRun: dryRunDisabled(),
    uploadStatus: uncertainStatus(),
    reconcile: [reconcilingStatus(), publishedStatus()],
  });

  await page.goto(`/jobs/${seeded.job.jobId}/publishing`);
  const card = page.locator(`#draft-${seeded.publishingId}`);
  await card.getByRole("button", { name: "Upload-Bereitschaft prüfen" }).click();

  // Warnung sichtbar.
  await expect(card.getByText(/nicht eindeutig/)).toBeVisible();
  await expect(card.getByText(/YouTube Studio/)).toBeVisible();
  await expect(card.getByText(/Starte keinen erneuten Upload/)).toBeVisible();

  // KEIN Upload-/Retry-Button.
  await expect(
    card.getByRole("button", { name: /hochladen/i }),
  ).toHaveCount(0);

  // Reconcile-Button vorhanden.
  const reconcileBtn = card.getByRole("button", { name: "Upload-Status prüfen" });
  await expect(reconcileBtn).toBeVisible();

  // 1. Klick → reconciling.
  await reconcileBtn.click();
  await expect(card.getByText(/Statusprüfung läuft\/steht an/)).toBeVisible();

  // 2. Klick → published (Recovery abgeschlossen).
  await card.getByRole("button", { name: "Upload-Status prüfen" }).click();
  await expect(card.getByText(/veröffentlicht \(privat\)/)).toBeVisible();
  await expect(card.getByText(/nicht eindeutig/)).toHaveCount(0);

  await expectNoSecretsInDom(page);
});
