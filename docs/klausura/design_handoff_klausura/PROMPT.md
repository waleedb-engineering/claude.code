# Start-Prompt für Claude Code

Diesen Text in Claude Code einfügen, nachdem der Ordner `design_handoff_klausura/` im Repo liegt (z. B. unter `docs/design/`).

---

Lies zuerst `design_handoff_klausura/README.md` vollständig. Es ist die verbindliche Spezifikation für KLAUSURA, ein Local-First-Lern-Cockpit für Ingenieurstudiengänge: 15 Screens in Desktop 1180 px und Mobile 390×844.

Die Datei `design_handoff_klausura/KLAUSURA.dc.html` ist eine **Design-Referenz**, kein Produktionscode: Inline-Styles, hartcodierte Beispieldaten, eigene Template-Runtime. Öffne sie im Browser, um Verhalten und Proportionen zu sehen — aber übersetze die Designs in die Patterns dieses Repos, statt HTML zu kopieren. Existiert hier noch keine Frontend-Umgebung, schlage eine vor und begründe sie, bevor du Code schreibst.

Fidelity ist hoch: Farben, Typografie, Abstände, Radien und Motion-Kurven stehen exakt im README und sind pixelgenau umzusetzen. Alle Zahlen im Prototyp sind Beispieldaten — Struktur übernehmen, Werte aus echten Daten speisen.

Bevor du beginnst:
1. Verschaffe dir einen Überblick über das Repo (Framework, State-Lösung, Styling-Ansatz, vorhandene Komponenten, Testing).
2. Melde mir, welche Bausteine aus dem Komponenten-Inventar (README Abschnitt 6) es hier schon gibt und welche neu entstehen müssen.
3. Arbeite dann `design_handoff_klausura/IMPLEMENTATION-PLAN.md` Paket für Paket ab, ein Paket pro Commit, und halte dich an `design_handoff_klausura/CLAUDE.md`.

Frage nach, statt zu raten, wenn eine Regel aus README Abschnitt 4 mit einer Konvention dieses Repos kollidiert.
