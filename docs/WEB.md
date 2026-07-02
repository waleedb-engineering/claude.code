# ClipForge AI — Web-App (lokal starten)

Minimale Next.js-UI über der FastAPI-Bridge. Die UI ruft **nur** die API auf —
keine Pipeline-Logik im Frontend, keine Datenbank, keine Accounts.

```
Browser ──► Next.js (web/, Port 3000) ──HTTP──► FastAPI (api/, Port 8000) ──► clipforge.run_pipeline
```

---

## Voraussetzungen

- Python 3.11+, FFmpeg (`sudo apt-get install -y ffmpeg`)
- Node.js 18+ (getestet mit Node 22)

---

## 1. Backend starten (Terminal A)

```bash
cd api
export PYTHONPATH=$PWD
pip install -r requirements.txt          # einmalig
uvicorn app:app --reload --port 8000
```

Check: <http://127.0.0.1:8000/health> liefert `{"status":"ok","ffmpeg":true,...}`.

## 2. Frontend starten (Terminal B)

```bash
cd web
npm install                              # einmalig
cp .env.example .env.local               # API-URL (Default passt lokal)
npm run dev                              # Entwicklung (Hot Reload)
# ODER produktionsnah:
#   npm run build && npm run start -- --port 3000
```

App öffnen: <http://127.0.0.1:3000>

> `NEXT_PUBLIC_API_BASE_URL` in `web/.env.local` zeigt standardmäßig auf
> `http://127.0.0.1:8000`. Bei anderem Backend-Port hier anpassen.
>
> Parallele Job-Verarbeitung: `CLIPFORGE_MAX_WORKERS` (Backend-ENV, Default 2).
> **Stabilität vor Geschwindigkeit** — bei großen Batches/Videos `=1` setzen
> (strikt seriell). Lokal, kein Cloud-Queue-System; keine Wiederaufnahme mitten
> im Render; große Batches können viel Speicher/CPU brauchen.

---

## Seiten

| Pfad | Inhalt |
|---|---|
| `/` | Landing mit „Video hochladen" |
| `/upload` | **Mehrfach-Upload** (Drag-and-drop, Datei-Liste mit Status je Datei), **Upload-Limits sichtbar**, gemeinsame Optionen, optionales Transkript-JSON **nur bei genau 1 Datei** |
| `/jobs` | **Queue-Summary** + **Storage-Widget** + Job-Liste mit Live-Status + **Abbrechen** (processing/queued) + **Job löschen** je Karte |
| `/jobs/[jobId]` | Status + Export-Counts, Clip-Karten, ZIP-Downloads (Auto & alle), **Bearbeiten**, Bereich „Manuelle Exporte" |
| `/jobs/[jobId]/clips/[clipIndex]/edit` | **Clip-Editor**: Start/Ende feinjustieren, **Caption-Style** (mit Beschreibung/Vorschau), neu rendern |
| `/settings/brand-kit` | **Brand Kit**: Farben, Default-Style, Highlight-Keywords, Watermark (lokal speichern) |

---

## Im Browser testen

1. <http://127.0.0.1:3000> öffnen → **Video hochladen**.
2. Ein Video wählen. Für einen schnellen, deterministischen Durchlauf ohne
   Whisper-Modell-Download zusätzlich das mitgelieferte Transkript als
   „Transkript (optional)" anhängen:
   - Video: `api/testdata/sample.mp4`
   - Transkript: `api/testdata/transcript.json`
3. Optional den Toggle **„Stille Pausen automatisch entfernen"** lassen (Default
   an) oder ausschalten. **Analyse starten** → Weiterleitung zur Job-Seite;
   Fortschritt erscheint live (inkl. Anzahl entfernter Stellen und Dauer).
4. Nach „Fertig" erscheinen die Clip-Karten mit **eingebetteter `<video>`-
   Vorschau**, Score, Aufschlüsselung, Begründung und Transkript-Ausschnitt.
   Bei aktivem Silence-Removal zeigt jede Karte zusätzlich kompakt
   **Original- → Final-Dauer, entfernte Stille und „Schnitt-Optimierung
   aktiv/inaktiv"** (plus Warnhinweis bei Fallback) sowie den verwendeten
   **Caption-Modus + -Style** (mit Fallback-Hinweis, falls keine Wort-Timestamps
   vorhanden waren) sowie die **Bildausrichtung** („Bild: Smart/Center/Face",
   inkl. „auf Gesicht ausgerichtet" bzw. Center-Fallback-Hinweis). Die
   Statuszeile zeigt erkannte Clips, exportierte MP4s, Downloads-Status,
   „Stille-Schnitt", „Captions" und „Bildausrichtung".
   Jede Karte enthält außerdem ein **aufklappbares „📦 Content-Paket"** mit
   fertig formulierten Plattform-Texten: Primary Hook, 5 Hook-Varianten,
   YouTube-Shorts-Titel/-Beschreibung, TikTok & Instagram-Reels-Caption +
   Hashtags + Pinned Comment, Platform-Empfehlung, 3 Varianten A/B/C. Alle
   Textfelder haben einen **„Kopieren"-Button**; pro Plattform gibt es
   „Alles kopieren". Funktioniert ohne API-Key (regelbasiert, DE+EN).
5. Clip direkt im Player **abspielen**, einzeln per **MP4 herunterladen**, oder
   als ZIP-Paket. Die Statuszeile zeigt zusätzlich **Auto-Clips**, **Manuelle
   Exporte** und **Gesamt-Exporte**. Zwei ZIP-Buttons:
   - **„Alle Clips als ZIP"** → `exports.zip` (unverändert, **nur Auto-Clips**,
     flach + clips.json/transcript.json/metadata.json/content_packages.json).
   - **„Alle Exporte als ZIP"** → `all-exports.zip` (**vollständiges Paket**:
     `auto_clips/` + `manual_exports/` + `data/` mit u. a. `manual_exports.json`
     und `metadata.json`).
6. Über **„Bearbeiten"** auf jeder Clip-Karte öffnet sich der **Clip-Editor**
   (`/jobs/[jobId]/clips/[clipIndex]/edit`): Vorschau des Auto-Clips, Felder für
   **Start-/Endzeit** (mit Live-Längenanzeige + Warnung bei <5s/>90s), **Titel**,
   **Caption-Style**, **Untertitel-Modus**, **Bildausrichtung** und **Stille-
   Pausen-Toggle**. **„Neu rendern"** erzeugt einen **separaten** manuellen Export
   (der Auto-Clip bleibt unangetastet); danach erscheinen neue Vorschau,
   Export-Metadaten und ein **Download-Button**. Bestehende manuelle Exporte des
   Clips werden darunter aufgelistet. Auf der Job-Seite zeigt die Clip-Karte
   zusätzlich einen Hinweis, wenn manuelle Exporte existieren.
7. Unter den Clip-Karten fasst der Bereich **„Manuelle Exporte"** alle
   manuellen Re-Renders **clip-übergreifend** zusammen: Titel, Quell-Clip,
   Start/Ende, finale Dauer, Caption-Style, Silence-Removal, Reframe-Modus,
   eine ein-/ausblendbare **Vorschau**, **Download**, ein **„Zum Editor"**-
   Link und ein **„Löschen"** (mit Inline-Bestätigung; entfernt nur diesen
   Export, Auto-Clips bleiben erhalten, Counts + all-exports.zip aktualisieren
   sich sofort).
8. **Job löschen:** sowohl in der Jobliste (pro Karte) als auch auf der
   Detailseite (Kopfzeile) gibt es **„Job löschen"** mit Inline-Bestätigung
   („Diesen Job wirklich löschen? …"). Läuft der Job gerade (`processing`), ist
   der Button deaktiviert. Nach dem Löschen verschwindet der Job aus der Liste
   bzw. die Detailseite navigiert zurück nach `/jobs`. Es wird der komplette
   lokale Job-Ordner entfernt — nie etwas außerhalb von `jobs/`.
9. **Batch-Upload (`/upload`):** ein oder mehrere Videos per Drag-and-drop /
   Mehrfachauswahl. Die Datei-Liste zeigt je Datei **Name, Größe und Status**
   (Wartet → Lädt hoch → Angenommen / Fehler). „Videos analysieren" legt pro
   Datei einen Job an (1 Datei → Einzel-Upload mit optionalem Transkript; >1 →
   Batch-Endpoint). Ungültige Dateien scheitern **einzeln** (per-Datei-Fehler),
   ohne die gültigen zu blockieren. Danach: **„Zur Queue"** und pro angenommener
   Datei **„Job öffnen"**.
10. **Queue-Summary (`/jobs`):** kompakte Zeile „Verarbeitet gerade / Wartet /
    Fertig / Fehlgeschlagen (/ Abgebrochen)", abgeleitet aus der (automatisch
    gepollten) Jobliste. Laufende Jobs zeigen einen Spinner-Badge;
    Details/Fortschritt auf der Job-Detailseite.
11. **Job abbrechen (`/jobs` + Detailseite):** `processing`/`queued`-Jobs haben
    einen **„Abbrechen"**-Button (amber) mit Inline-Bestätigung („Diesen Job
    wirklich abbrechen? Bereits erzeugte Dateien können erhalten bleiben."). Nach
    Klick zeigt der Button „Abbruch läuft …"; der Job wechselt **kooperativ** (am
    nächsten sicheren Checkpoint, kann Sekunden dauern) auf **„Abgebrochen"**.
    Danach ist der Abbrechen-Button weg, **Löschen** bleibt möglich. Für
    `canceled`-Jobs werden **keine** Download-Buttons gezeigt (die Detailseite
    rendert Downloads nur für `completed`).
12. **Upload-Limits (`/upload`):** unter der Drop-Zone stehen die aktiven Limits
    (max. Dateien/Batch · max. MB/Datei aus `GET /api/config`). Zu viele Dateien
    → sofortige Fehlermeldung, die Liste wird auf das Maximum begrenzt; eine zu
    große Datei wird in der Liste als „zu groß" markiert und vom Backend
    abgelehnt (Batch: nur diese Datei; Einzel: `413`).
13. **Storage-Widget (oben auf `/jobs`):** zeigt lokalen Gesamtspeicher, Anzahl
   Jobs, Auto-/Manuelle Exporte, die **Status-Verteilung** (Fertig, Fehlgeschlagen,
   Unterbrochen, Unvollständig, Läuft, Warteschlange) und die **größten Jobs**.
   Der Button **„Problematische Jobs aufräumen (N)"** löscht nach Inline-
   Bestätigung gesammelt nur `failed`/`interrupted`/`incomplete`-Jobs
   (`completed` bleibt erhalten, `processing` ist geschützt); danach zeigt es
   „X gelöscht · Y freigegeben" und Liste + Widget aktualisieren sich. Gibt es
   keine Kandidaten, ist der Button deaktiviert („Keine problematischen Jobs zum
   Aufräumen").
14. **Caption-Styles (`/upload` + Editor):** Auswahl aus 5 Styles (clean,
    bold_creator, high_energy, podcast, minimal) mit **Beschreibung** und einer
    kleinen **CSS-Vorschau** (nur Näherung — die FFmpeg-Ausgabe ist maßgeblich).
    Bei Batch gilt der gewählte Style für alle Jobs.
16. **Clip-Analyzer v2 (Clip-Karten + Job-Seite):** Der Score bleibt prominent
    (Ring) und ist in **Bänder kalibriert** (schwach/solide/gut/sehr stark).
    Jede Clip-Karte zeigt kompakt **Hook-Typ**, **Clip-Typ**, **beste
    Plattform**, **Analyzer-Modus + v2** (Regelbasiert/KI/Fallback) und — falls
    gesetzt — die **Dedup-Gruppe**. Dazu **Risk-Flags** mit lesbaren deutschen
    Labels aus stabilen englischen Keys (z. B. „braucht Kontext" =
    `needs_context`, „schwacher Hook" = `weak_hook`, „ähnelt anderem Clip" =
    `duplicate_like`, „Sprachmix" = `language_mixed`) und ausklappbar der
    **10-Komponenten-Score** + **Verbesserungsvorschläge** (aus den Flags
    abgeleitet). Die Job-Detailseite zeigt oben eine Zeile „Analyzer: v2 · Modus ·
    Kandidaten · nach Dedup" — plus „aufgefüllt" (wenn Vielfalt knapp war) und
    „LLM: … ms" (nach echtem LLM-Lauf). Auf `/upload` gibt es den Toggle
    **„Erweiterte Clip-Analyse verwenden"** (Default an; ohne API-Key läuft es
    regelbasiert). Alte Clips ohne v2-Felder werden weiter angezeigt (ohne
    v2-Panel), nichts crasht.
17. **Brand Kit (`/settings/brand-kit`, Nav-Link „Brand Kit"):** Brand Name,
    Primary/Secondary Color (Color-Picker + Hex), Default-Caption-Style,
    Highlight-Keywords (Komma-Liste), Watermark-Text + An/Aus, **Speichern** mit
    Erfolgs-/Fehlermeldung. Ist ein Brand Kit gespeichert, zeigen Upload und
    Editor **„🎨 Brand Kit aktiv: {name}"** und nutzen dessen Default-Style; die
    Marken-Farben/Watermark werden beim Rendern angewandt. Nach einem Re-Render
    zeigen die Export-Metadaten `caption_style` und `Brand Kit an/aus`.
18. **Publishing Planner (`/jobs/{jobId}/publishing`):** Über **„Publishing
    vorbereiten"** auf jeder Clip-Karte und bei manuellen Exporten erreichbar
    (Prefill via `?clip=` / `?export=`). Drafts anlegen (Plattform: YouTube
    Shorts/TikTok/Instagram Reels; Texte kommen aus dem Content-Paket),
    bearbeiten (Titel/Caption/Beschreibung/Hashtags/Pinned Comment/geplantes
    Datum), **Prüfen** (erweiterte Checkliste: blockierende Probleme getrennt
    von Qualitäts-Hinweisen wie „Titel zu lang" oder „Termin liegt in der
    Vergangenheit" → Status „Bereit"), **Duplizieren** (auch mit
    Plattformwechsel), **Publishing Pack (ZIP)** herunterladen und löschen.
    Jeder Draft trägt ein **„🔒 lokal"**-Badge. **Kein automatischer Upload,
    kein Plattform-Login** — Plan für die echte Anbindung:
    [`PUBLISHING_AGENT_PLAN.md`](PUBLISHING_AGENT_PLAN.md).
19. **Globale Publishing-Übersicht (`/publishing`, Nav-Link „Publishing"):**
    alle Drafts über alle Jobs zentral, mit Summary-Cards (Gesamt/Bereit/
    Geplant/Ungültig/Plattform-Zähler) und Filtern (Plattform, Status, Suche,
    „nur geplante"). Jede Draft-Karte zeigt Quelle (Job + Auto-Clip/Export),
    kleine Vorschau, Validierungsstatus, und Buttons „Zum Planner", „Pack
    (ZIP)", „Duplizieren". Die Job-Detailseite zeigt dazu eine kompakte
    **Publishing-Badge-Zeile** („Publishing Drafts: X · Bereit: Y · Ungültig:
    Z") mit Link „Publishing öffnen", sobald Drafts existieren. Weiterhin
    **kein echtes Posten, keine OAuth-Anzeige als wäre sie aktiv**.
20. **YouTube Dry-Run (im Planner, nur bei YouTube-Shorts-Drafts):** Button
    **„YouTube Dry-Run prüfen"** zeigt, was hochgeladen *würde* —
    Privacy-Status, „würde hochladen ja/nein", Checks (MP4, 9:16, Titel,
    Beschreibung, keine Viralitätsgarantie, Feature-Flag aktiv, Credentials
    konfiguriert), Blocker, Hinweise und eine Request-Vorschau (Metadaten,
    **kein Token, kein Video-Body**). Ist der Upload deaktiviert, steht klar
    **„🔒 Echter YouTube Upload ist deaktiviert. Dry-Run only."**. Es gibt
    **keinen „Live veröffentlichen"-Button** und **kein OAuth-UI** in dieser
    Phase. Nicht-YouTube-Drafts zeigen dieses Panel nicht. Details:
    [`YOUTUBE_PUBLISHING.md`](YOUTUBE_PUBLISHING.md).

> Echtes Video **ohne** angehängtes Transkript: Die Pipeline transkribiert dann
> lokal mit faster-whisper. Beim ersten Lauf wird das Modell geladen (~140 MB),
> daher dauert der erste Durchlauf länger.

---

## Zustände in der UI

- **Loading:** Spinner auf Job- und Übersichtsseiten.
- **Processing:** Live-Log + automatisches Polling (alle 2 s).
- **Empty:** „Noch keine Jobs" bzw. Hinweis bei leerem Ergebnis (0 Clips).
- **Error:** Verständliche Meldung bei Backend-Ausfall, ungültigem Dateityp,
  fehlgeschlagener Analyse (`job.error`) oder nicht gefundenem Job.
- **Wiederhergestellt (Restore):** Jobs überleben einen FastAPI-Neustart. Sie
  werden aus `jobs/` neu geladen und in Liste + Detailseite mit dem Hinweis
  **„↻ Aus lokalem Speicher wiederhergestellt"** markiert. Voll nutzbar bleiben
  Clips, Previews/Downloads, manuelle Exporte und beide ZIPs — ohne erneute
  Analyse.
- **Unterbrochen / Unvollständig:** War ein Job beim Neustart aktiv, wird er als
  **„Unterbrochen"** (`interrupted`) angezeigt — mit klarer Erklärung und
  **ohne** irreführende Download-Buttons. Fehlen einem fertigen Job die
  Ergebnis-Dateien, erscheint **„Unvollständig"** (`incomplete`) mit Warnhinweis.

---

## Nicht enthalten (bewusst)

❌ Accounts · ❌ Billing · ❌ Cloud · ❌ Face-Tracking · ❌ Direkt-Posten auf
TikTok/Instagram/YouTube · ❌ neue Backend-Logik · ❌ Datenbank ·
❌ Cloud-Persistenz · ❌ automatische Wiederaufnahme laufender Renders nach Crash ·
❌ externe/mitgelieferte Fonts · ❌ Brand-Kit-Cloud-Sync (nur lokale JSON).
