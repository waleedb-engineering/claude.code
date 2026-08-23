# KLAUSURA

Local-First-Lern-App für Ingenieurklausuren. Spezifikation in
[`../docs/klausura/`](../docs/klausura/), Design-Referenz in
`../docs/klausura/design_handoff_klausura/`.

## Stand: M0 + M1

| Bereich | Zustand |
|---|---|
| Domänen-Kern, Modell, Persistenz | fertig, 111 Tests |
| Desktop: Import, Segmentierung, Atlas, Solve | fertig, E2E-verifiziert |
| Tauri-Hülle | konfiguriert, **hier nicht übersetzbar** |
| Mobile (Expo): Atlas, Solve | geschrieben, **nicht ausgeführt** |

## Aufbau

```
packages/model           Entitäten und Invarianten
packages/ports           Verträge: Storage, Clock, Pdf, Blob, Ocr, Llm
packages/core            reine Domäne — kein IO, keine Uhr, kein Zufall
packages/storage-sqlite  Migrationen, Repositories, sql.js-Adapter
packages/adapters-fake   Attrappen für Test und Offline-Entwicklung
packages/ui-tokens       Farben, Typo, Spacing, Motion aus dem Handoff
apps/desktop             Vite + React; läuft im Browser und in Tauri
apps/mobile              Expo; Atlas und Solve
```

`packages/core` darf nur `model` und `ports` importieren. Kein `Date.now()`,
kein `Math.random()`, kein `fetch` — die ESLint-Grenzregel erzwingt das.

## Befehle

```bash
pnpm install

pnpm test          # 111 Unit-Tests, Node
pnpm lint          # inkl. Grenzregel für core
pnpm typecheck

pnpm dev:desktop   # http://localhost:5183
pnpm test:e2e      # Playwright, headless

pnpm --filter @klausura/desktop dev:tauri     # nur macOS
pnpm --filter @klausura/mobile dev            # nur mit Simulator
```

## Was in M1 bewusst fehlt

Keine Auto-Segmentierung, kein OCR, kein LLM. `OcrPort` und `LlmPort`
existieren als Vertrag mit Attrappe, sonst nichts. Bewertung beschränkt sich
auf das Erfassen von Wert und Einheit; die fünf Solve-Zustände und die
Fehler-DNA sind M2.
