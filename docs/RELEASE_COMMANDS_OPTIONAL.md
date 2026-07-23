# Release Commands (OPTIONAL — nur vorbereitet, NICHT ausgeführt)

> ⚠️ **Nur ausführen, wenn Walid ausdrücklich freigibt.**
>
> Keiner der folgenden Befehle wurde von ClipForge/dem Automations-Workflow
> ausgeführt. Sie sind **externe, teils schwer reversible Aktionen** (Tags,
> Releases, PRs). Vor der Ausführung: aktuellen Stand prüfen, gewünschtes
> Ziel-/Base-Branch bestätigen, und den YouTube-Real-Test-Status
> (siehe [`RELEASE_DECISION.md`](RELEASE_DECISION.md)) bewusst einordnen.

Voraussetzung für alle Befehle: sauberer, gepushter Stand auf
`claude/ai-video-shorts-tool-hjct7s`, `release_check.sh` = PASS.

---

## 1. Annotiertes Git-Tag `v0.1.0-beta.1`

```bash
# Tag auf den aktuellen (grünen) Commit setzen:
git tag -a v0.1.0-beta.1 -m "ClipForge AI 0.1.0-beta.1 — closed beta / release candidate"

# Tag zum Remote pushen:
git push origin v0.1.0-beta.1
```

Rückgängig (falls nötig, solange niemand den Tag gezogen hat):

```bash
git tag -d v0.1.0-beta.1
git push origin :refs/tags/v0.1.0-beta.1
```

## 2. GitHub Pre-Release (als Beta markiert)

> Nur als **Pre-release** veröffentlichen, nie als „Latest". Das Beta-Package
> vorher mit `./scripts/build_beta_package.sh` bauen.

```bash
# Voraussetzung: gh CLI authentifiziert, Tag v0.1.0-beta.1 existiert bereits.
./scripts/build_beta_package.sh   # erzeugt dist/clipforge-beta-0.1.0-beta.1.tar.gz

gh release create v0.1.0-beta.1 \
  dist/clipforge-beta-0.1.0-beta.1.tar.gz \
  --prerelease \
  --title "ClipForge AI 0.1.0-beta.1 (closed beta)" \
  --notes-file docs/RELEASE_NOTES_0.1.0-beta.1.md
```

## 3. Pull Request (falls ein Merge in einen Basis-Branch gewünscht ist)

> Base-Branch bewusst wählen. In diesem Setup ist der Arbeits-/Default-Branch
> `claude/ai-video-shorts-tool-hjct7s`; ein PR ergibt nur Sinn, wenn ein
> separater Integrations-Branch (z. B. `main`) existiert. `<BASE>` ersetzen.

```bash
# gh CLI:
gh pr create \
  --base <BASE> \
  --head claude/ai-video-shorts-tool-hjct7s \
  --title "ClipForge AI 0.1.0-beta.1 — beta hardening & release candidate" \
  --body-file docs/RELEASE_NOTES_0.1.0-beta.1.md
```

---

## Reihenfolge-Empfehlung (falls freigegeben)

1. `release_check.sh` erneut ausführen → PASS bestätigen.
2. (Empfohlen) YouTube-Real-Test nach Checkliste durchführen und Ergebnis
   dokumentieren.
3. Tag `v0.1.0-beta.1` setzen + pushen.
4. Optional: Pre-Release mit angehängtem Package erstellen.
5. Optional: PR öffnen, falls ein Integrations-Branch existiert.

**Erneuter Hinweis:** Nichts davon ohne ausdrückliche Freigabe ausführen.
