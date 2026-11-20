import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow J — Stream Intelligence: Quelle anlegen (Rechte), VOD + Chat-Export
// hochladen, Highlights finden (echtes FFmpeg, ohne Transkription), Begründung
// sehen, Vorschau rendern. Kein Netz, keine Kosten.
// ---------------------------------------------------------------------------

function makeVod(): string {
  const dir = mkdtempSync(join(tmpdir(), "cf-e2e-stream-"));
  const out = join(dir, "vod.mp4");
  execFileSync("ffmpeg", [
    "-v", "error", "-y",
    "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=60:r=10",
    "-f", "lavfi", "-i", "testsrc=s=320x180:d=10:r=10",
    "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=50:r=10",
    "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.02:d=60",
    "-f", "lavfi", "-i", "sine=f=1800:d=10,volume=6",
    "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.02:d=50",
    "-filter_complex", "[0:v][3:a][1:v][4:a][2:v][5:a]concat=n=3:v=1:a=1[v][a]",
    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", out,
  ]);
  return out;
}

function chatExport(): Buffer {
  const comments = [];
  for (let t = 0; t < 120; t += 1) {
    comments.push({ content_offset_seconds: t + 0.3, commenter: { display_name: `u${t % 30}` }, message: { body: "hallo", fragments: [] } });
  }
  for (let i = 0; i < 80; i += 1) {
    comments.push({ content_offset_seconds: 65 + (i % 40) / 10, commenter: { display_name: `fan${i}` }, message: { body: "KEKW no way", fragments: [] } });
  }
  return Buffer.from(JSON.stringify({ comments }));
}

test("Streams: VOD + Chat → Highlights mit Begründung → Vorschau", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/studio/streams");
  await expect(page.getByRole("heading", { name: "Stream Intelligence" })).toBeVisible();
  await page.getByLabel("Titel").fill(`${E2E_PREFIX} Stream`);
  const create = page.getByRole("button", { name: "Anlegen" });
  await expect(create).toBeDisabled(); // ohne Rechtebestätigung kein Anlegen
  await page.getByLabel(/Ich darf diese Aufnahme/).check();
  await create.click();
  await page.waitForURL(/\/studio\/streams\/[a-f0-9]{12}$/);
  const sid = page.url().split("/").pop() as string;
  try {
    await page.getByLabel("Video (VOD/OBS-Aufnahme)").setInputFiles(makeVod());
    await expect(page.getByText(/✓ vod\.mp4/)).toBeVisible({ timeout: 60_000 });
    await page.getByLabel("Chat-Export (optional)").setInputFiles({ name: "chat.json", mimeType: "application/json", buffer: chatExport() });
    await expect(page.getByText(/Nachrichten · \d+ Chatter · twitchdownloader/)).toBeVisible();
    await page.getByLabel(/Sprache in den Kandidaten-Fenstern/).uncheck();
    await page.getByRole("button", { name: "Highlights finden" }).click();
    await expect(page.getByText(/Signale: audio, chat, video/)).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText(/Chat-Aktivität: \+\d+ Punkte/).first()).toBeVisible();
    await page.getByRole("button", { name: "▶ Vorschau" }).first().click();
    await expect(page.locator("video").first()).toBeVisible({ timeout: 60_000 });
    // Variante wählen, als echt markieren, auswerten
    await page.getByRole("button", { name: /^Mehr Kontext · \d+ s · Eignung \d+$/ }).first().click();
    await expect(page.getByText(/ · context$/).first()).toBeVisible();
    await page.getByRole("button", { name: "✓ echtes Highlight" }).first().click();
    await expect(page.getByText(/ · ✓$/).first()).toBeVisible();
    await page.getByRole("button", { name: "Auswerten" }).click();
    await expect(page.getByTestId("stream-eval")).toContainText(/Treffer 1/);
  } finally {
    await fetch(`${API_URL}/api/studio/streams/${sid}`, { method: "DELETE", headers: { "X-ClipForge-Token": process.env.E2E_API_TOKEN ?? "e2e-local-token-0123456789abcdef" } });
  }
});
