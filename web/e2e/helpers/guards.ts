import { test as base, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Zentrale Fehler-Wächter (Aufgabe 11).
//
// Jeder Test scheitert automatisch bei unerwarteten Browser-Fehlern:
//   • console.error
//   • pageerror (unbehandelte Exceptions)
//   • unhandledrejection (per Init-Script in console.error umgeleitet)
//
// KEINE pauschale Ignore-Liste. Ein Test darf einzelne, klar begründete Muster
// per `errors.allow(/…/)` freigeben (z. B. der bewusst provozierte
// „Backend nicht erreichbar“-Fall). Alles andere lässt den Test fehlschlagen.
// ---------------------------------------------------------------------------

export interface CapturedError {
  kind: "console" | "pageerror";
  text: string;
}

export class ErrorSink {
  private readonly errors: CapturedError[] = [];
  private readonly allowed: RegExp[] = [];

  record(kind: CapturedError["kind"], text: string): void {
    this.errors.push({ kind, text });
  }

  /** Ein konkretes, erwartetes Fehlermuster für diesen Test freigeben. */
  allow(pattern: RegExp): void {
    this.allowed.push(pattern);
  }

  unexpected(): CapturedError[] {
    return this.errors.filter(
      (e) => !this.allowed.some((re) => re.test(e.text)),
    );
  }

  assertClean(): void {
    const bad = this.unexpected();
    expect(
      bad,
      `Unerwartete Browser-Fehler:\n${bad
        .map((e) => `  [${e.kind}] ${e.text}`)
        .join("\n")}`,
    ).toEqual([]);
  }
}

async function attachGuards(page: Page, sink: ErrorSink): Promise<void> {
  // unhandledrejection im Seitenkontext in console.error umleiten, damit der
  // Console-Wächter greift. Init-Script gilt für alle folgenden Navigationen.
  await page.addInitScript(() => {
    window.addEventListener("unhandledrejection", (event) => {
      const reason = event.reason;
      const msg =
        reason && typeof reason === "object" && "message" in reason
          ? (reason as { message?: string }).message
          : String(reason);
      console.error(`[unhandledrejection] ${msg}`);
    });
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") sink.record("console", msg.text());
  });
  page.on("pageerror", (err) => {
    sink.record("pageerror", err.message);
  });
}

export const test = base.extend<{ errors: ErrorSink }>({
  errors: [
    async ({ page }, use) => {
      const sink = new ErrorSink();
      await attachGuards(page, sink);
      await use(sink);
      sink.assertClean();
    },
    { auto: true },
  ],
});

export { expect };
