# Publishing-Agent — Plan & Safe MVP

Stand: 2026-07-03. Dieses Dokument ist der verbindliche Plan für den späteren
Publishing-Agent. **YouTube hat jetzt einen echten, aber ausschließlich
PRIVATEN Uploadpfad** (`videos.insert`, hinter Feature-Flag +
`UPLOAD_PRIVATE`-Bestätigung + Idempotenz + Token-Refresh, Phase 3, siehe
[`YOUTUBE_PUBLISHING.md`](YOUTUBE_PUBLISHING.md) §7d). **Kein public/unlisted,
kein Auto-Posting, kein TikTok/Instagram-Upload.** Tokens leben nur im
OS-Keychain, nie in ENV/Datei/Response/Logs; `client_secret`/`id_token` werden
nie gespeichert; `published`/`external_post_id` nur bei eindeutigem API-Erfolg.

## 1. Ziel

ClipForge AI soll fertige Clips später halbautomatisch oder automatisch auf
**YouTube Shorts, TikTok und Instagram Reels** veröffentlichen können — aber
ausschließlich über **offizielle, erlaubte APIs**. Keine Bot-Umgehung, kein
Scraping, keine Browser-Automation gegen Plattformregeln, keine falschen
Versprechen.

## 2. Was aktuell möglich ist (Bestand)

| Baustein | Ort | Publishing-relevant |
|---|---|---|
| Auto-Clips (MP4) | `jobs/{job_id}/clip_NN_scoreXX.mp4` (`output_path` in `clips.json`) | ✅ Hauptquelle |
| Manuelle Re-Renders | `jobs/{job_id}/manual_exports/{export_id}.mp4` + `.json` | ✅ zweite Quelle |
| Content Packages | pro Clip in `clips.json` → `content_package` (auch in `content_packages.json` der ZIPs) | ✅ liefert Titel/Caption/Hashtags |
| Pro Clip vorhanden | MP4, Titel (`youtube_shorts.title`), Beschreibung, Captions, Hashtags, Pinned Comment, Plattform-Empfehlung, Varianten A/B/C, Score v2, Risk-Flags | ✅ |
| Brand Kit | `brand_kit.json` (Name, Farben, Caption-Style, Watermark) | teilweise (Branding steckt schon im Video) |
| ZIP-Exporte | `exports.zip`, `all-exports.zip` | ✅ Vorbild fürs Publishing Pack |

**UI-Bereiche für Erweiterung:** Job-Detailseite (Einstieg pro Clip),
Manual-Exports-Bereich (Einstieg pro Export), Editor (später „direkt planen"),
neue Seite `/jobs/{jobId}/publishing` (Planner).

**Technische Risiken (bewertet):** OAuth-Flows + Token-Speicherung (höchstes
Risiko — braucht Verschlüsselungs-/Sicherheitskonzept), App-Reviews/API-
Freigaben (Wochen an Vorlauf), Rate Limits, Plattformregel-Verstöße,
Scheduling-Zuverlässigkeit (lokaler Prozess läuft nicht immer), Upload-Fehler
und **Doppel-Posts** (braucht Idempotenz über `external_post_id`), falsche
Metadaten, Datenschutz (Tokens/Analytics sind personenbezogen).

**Entscheidung:** Erst ein lokales, API-freies **Publishing-Planner-MVP**
(umgesetzt, siehe §5). Echte Uploads erst ab Phase 2, beginnend mit YouTube
(am besten dokumentierter Weg), niemals ohne Nutzer-Bestätigung.

## 3. Was noch NICHT gebaut wird

- Kein OAuth-Flow, keine Token-Speicherung (auch nicht „nur kurz in .env").
- Kein Upload/Post zu YouTube/TikTok/Instagram, keine externen API-Calls.
- Kein Hintergrund-Scheduler (geplante Zeiten sind nur gespeicherte Metadaten).
- Keine Analytics-Anbindung.

## 4. Plattform-Realitätscheck

Geprüft am 2026-07-02 gegen die offiziellen Doku-Seiten (abgerufen):

### YouTube Shorts — `developers.google.com/youtube/v3/docs/videos/insert`
- ✅ Upload per API möglich (`videos.insert`), max. 256 GB.
- ✅ Titel/Beschreibung/Tags (`snippet.*`), Privacy-Status (`status.privacyStatus`).
- ✅ **Scheduling möglich** (`status.publishAt`).
- 🔐 OAuth nötig (u. a. Scope `youtube.upload`).
- ⚠️ **Einschränkung:** Uploads aus *unverifizierten* API-Projekten (erstellt
  nach 28.07.2020) sind auf **privat** beschränkt, bis ein Audit besteht.
  Quota-Kosten pro Upload beachten.

### TikTok — `developers.tiktok.com/doc/content-posting-api-get-started/`
- ✅ Content Posting API: **Direct Post und Draft-Upload** (FILE_UPLOAD oder
  PULL_FROM_URL), MP4/H.264.
- 🔐 OAuth über Login Kit; Scope **`video.publish`** muss beantragt/genehmigt sein.
- ⚠️ **App-Review/Audit Pflicht:** Inhalte unauditierter Apps sind auf
  **privat** beschränkt. Video-Längenlimits kommen aus der Creator-Info-Abfrage.

### Instagram Reels — `developers.facebook.com/docs/instagram-api/guides/content-publishing/`
- ✅ Reels per Graph API (`media_type=REELS` Container → publish).
- 🔐 **Professional-Account** (Business/Creator) nötig; Login via Instagram-
  oder Facebook-Login (Page-Verknüpfung), Scopes wie `instagram_content_publish`.
- ⚠️ **Kein API-Scheduling** (Veröffentlichung ist sofort). Limit **100
  API-Posts pro 24 h**. Größte Hürde für local-first: das Video muss zum
  Upload auf einem **öffentlich erreichbaren Server** liegen — direkter
  Datei-Upload vom lokalen Rechner ist nicht vorgesehen.

**TODO (vor Phase 2/3 erneut offiziell prüfen):** exakte YouTube-Quota-Kosten
pro Upload, aktueller TikTok-Audit-Prozess & Limits, Meta-App-Review-Umfang,
ob sich Hosting-Anforderungen (Instagram) geändert haben.

## 5. Safe MVP: Publishing Planner ✅ (umgesetzt)

Lokal, ohne jedes API-Risiko:

1. Nutzer wählt fertigen Clip (Auto-Clip oder manuellen Export).
2. Nutzer wählt Plattform (YouTube Shorts / TikTok / Instagram Reels).
3. Titel/Caption/Hashtags/Pinned Comment werden aus dem Content Package
   vorbefüllt und sind frei editierbar.
4. Optionales geplantes Datum (nur Metadaten, kein Hintergrund-Job).
5. Draft wird lokal gespeichert (siehe Datenmodell).
6. Checkliste: MP4 bereit · 9:16 · Titel · Caption · Hashtags · Plattform ·
   keine Viralitätsversprechen.
7. **Publishing Pack (ZIP):** MP4 + `metadata.json` + `caption.txt` +
   `description.txt` + `platform_notes.txt` (Hinweise für den manuellen Upload).
8. **Kein echter Plattform-Upload.**

**Erweiterung (Prompt 22) ✅:** Der Planner ist jetzt auch **jobübergreifend**
nutzbar — eine globale Übersicht listet, filtert und dupliziert Drafts über
alle Jobs hinweg, ohne den Scope zu erweitern (weiterhin kein Upload/OAuth/Token).

## 6. Datenmodell (lokal, ohne Datenbank) ✅

Speicherort: `jobs/{job_id}/publishing/{publishing_id}.json` (eine Datei pro
Draft; IDs sind 12-stellige Hex-Strings, Path-Traversal wird geblockt).

Felder: `publishing_id`, `job_id`, `source_type` (auto_clip|manual_export),
`source_clip_index?`, `manual_export_id?`, `mp4_path`, `platform`, `title`,
`caption`, `description`, `hashtags[]`, `pinned_comment?`, `scheduled_at?`,
`status`, `validation` (passed + checks + checked_at + **`summary`**, s. u.),
`created_at`, `updated_at`, `published_at?`, `external_post_id?` (erst später),
`error?`, `duplicated_from?` (gesetzt bei Duplikaten), `warning?` (z. B. wenn
beim Duplizieren die Texte nicht plattformspezifisch neu abgeleitet werden
konnten).

Status: `draft → ready → scheduled → publishing → published | failed |
canceled`. Im Planner sind nur `draft/ready/scheduled/canceled` setzbar;
`publishing/published/failed` sind für den echten Publisher reserviert
(verhindert vorgetäuschte Veröffentlichungen). `ready` wird von der
Validierung gesetzt/entzogen.

**`validation.summary`** (Prompt 22) fasst die Checkliste zusammen:
`is_valid`, `blocking_issues_count`, `blocking_issues[]`, `warnings_count`,
`checklist` (`mp4_exists`, `format_9_16`, `title_present`, `caption_present`,
`hashtags_present`, `platform_selected`, `no_viral_guarantee`, `safe_status`),
`quality_hints[]` (`title_too_long`, `caption_too_long`, `too_many_hashtags`,
`missing_pinned_comment`, `scheduled_in_past`, `weak_metadata`). Die
Quality-Hints sind **grobe lokale Richtwerte, keine offiziellen
Plattform-Limits** (siehe TODOs in §4).

## 7. API-Plan ✅ (umgesetzt, nur lokal)

| Endpoint | Zweck |
|---|---|
| `GET /api/publishing` | **Globale Übersicht** über alle Jobs — Filter `status`, `platform`, `job_id`, `q`, `scheduled_only` |
| `GET /api/jobs/{job_id}/publishing` | Drafts eines Jobs listen |
| `POST /api/jobs/{job_id}/publishing` | Draft anlegen (Prefill aus Content Package) |
| `GET /api/jobs/{job_id}/publishing/{publishing_id}` | Draft lesen |
| `PATCH /api/jobs/{job_id}/publishing/{publishing_id}` | Texte/Plattform/Status bearbeiten |
| `DELETE /api/jobs/{job_id}/publishing/{publishing_id}` | Draft löschen |
| `POST …/{publishing_id}/validate` | lokale Validierung (MP4, 9:16 via ffprobe, Texte, Claims) + `summary` |
| `POST …/{publishing_id}/duplicate` | **Draft duplizieren** (neue ID, optional andere Plattform, optional Zeitplan übernehmen) |
| `GET …/{publishing_id}/pack.zip` | Publishing Pack (ZIP) |

Kein Endpoint macht externe Aufrufe. `GET /api/publishing` scannt
`jobs/*/publishing/` read-only; defekte Draft-Dateien oder Job-Ordner lassen
den Endpoint nicht crashen (Skip + `warnings[]` in der Antwort).

`POST …/duplicate` (Body: `{platform?, copy_schedule}`) — beim
Plattformwechsel wird versucht, Titel/Caption/Hashtags aus dem Content-Paket
der ursprünglichen Quelle für die neue Plattform abzuleiten; gelingt das
nicht, werden die Original-Texte übernommen und ein `warning` gesetzt. Ohne
`copy_schedule: true` wird `scheduled_at` nicht übernommen. Das Original
bleibt unverändert.

## 8. UI-Plan ✅ (umgesetzt)

- Job-Detailseite: Button **„Publishing vorbereiten"** auf jeder Clip-Karte
  und bei jedem manuellen Export (Prefill via `?clip=` / `?export=`); dazu
  eine kompakte **Publishing-Badge-Zeile** (Drafts/Bereit/Ungültig/Geplant +
  Button „Publishing öffnen"), wenn für den Job Drafts existieren.
- Seite **`/jobs/{jobId}/publishing`**: Draft-Liste, Neuer-Draft-Formular
  (Quelle + Plattform), Editierfelder (Titel/Caption/Beschreibung/Hashtags/
  Pinned Comment/geplantes Datum), Clip-Preview, **erweiterte
  Validierungs-Checkliste** (blockierende Probleme + Warnhinweise getrennt,
  inkl. Warnung bei Termin in der Vergangenheit), **Duplizieren**-Funktion,
  Status-Chips, Pack-Download, „🔒 lokal"-Badge pro Draft. Deutlicher Hinweis:
  *kein automatischer Upload*.
- **Neue globale Seite `/publishing`** (Nav-Link „Publishing"): Summary-Cards
  (Gesamt/Bereit/Geplant/Ungültig/Plattform-Zähler), Filter (Plattform, Status,
  Suche, „nur geplante"), Draft-Karten mit Quelle (Job + Clip/Export),
  Vorschau, Validierungsstatus, Zum-Planner-/Pack-/Duplizieren-Buttons.

## 9. Architektur-Zielbild (späterer echter Publisher)

```
PublishingService  (zentrale Schnittstelle; nimmt Draft + Plattform,
  │                 validiert IMMER vor Upload, erzwingt Nutzer-Bestätigung)
  ├── ValidationService   ✅ heute schon (validate_draft)
  ├── PublishingQueue     lokale Queue über die Draft-JSONs (Status-Feld);
  │                       Worker verarbeitet 'scheduled' → 'publishing'
  ├── PublishingJob       = ein Draft (Datenmodell §6, bereits kompatibel)
  ├── AuthService         NUR Interface/TODO: get_token(platform),
  │                       refresh(platform); Implementierung erst mit
  │                       Verschlüsselungs-Konzept (OS-Keychain o. ä.)
  └── PlatformAdapter     gemeinsames Interface:
        ├── YouTubeAdapter    (videos.insert, publishAt)      → Phase 2
        ├── TikTokAdapter     (Content Posting API, Audit)    → Phase 3
        └── InstagramAdapter  (Graph API, Hosting-Frage!)     → Phase 3
```

Adapter-Interface (geplant): `preflight(draft) → list[str]`,
`upload(draft, confirm_token) → external_post_id`, `capabilities() →
{scheduling: bool, draft_mode: bool, max_duration_s: int}`. Idempotenz:
vor jedem Upload `external_post_id` prüfen — gesetzt ⇒ niemals erneut posten.

## 10. Sicherheits- & Compliance-Regeln (hart)

1. Kein echtes Posten ohne offizielle API.
2. Keine OAuth-Token-Speicherung ohne Verschlüsselungs-/Sicherheitskonzept.
3. Kein Scraping.
4. Keine Browser-Automation gegen Plattformregeln.
5. Keine Fake-Views/-Likes/-Kommentare.
6. Keine Viralitätsgarantie (die Validierung blockt solche Formulierungen
   sogar aktiv in Publishing-Texten).
7. Nutzer muss vor jedem echten Post explizit bestätigen.
8. Logs enthalten keine Secrets/Tokens.
9. Publishing-Status ist nachvollziehbar (Status + Timestamps + validation im Draft).
10. Fehlgeschlagene Uploads werden nie blind wiederholt — Idempotenz über
    `external_post_id`, Retry nur nach Statusprüfung.

## 11. Roadmap

| Phase | Inhalt | Voraussetzung |
|---|---|---|
| **1 (✅ jetzt)** | Publishing Planner lokal (Drafts, Validierung, Pack-ZIP, **globale Übersicht + Duplizieren**, Prompt 21+22) | — |
| 2 | YouTube-Upload über offizielle API — **Dry-Run (Ph. 1) + OAuth-Readiness/keyring (Ph. 2) + OAuth-Flow inkl. echtem Token-Exchange (Ph. 2b/2c) + echter PRIVATER Upload `videos.insert` mit Idempotenz + Token-Refresh (Ph. 3) + Hardening: Retry/Backoff, Attempt-History, `upload-status`/Reauth, sicherer manueller Real-Testmodus (Ph. 3b) gebaut**, siehe [`YOUTUBE_PUBLISHING.md`](YOUTUBE_PUBLISHING.md). **Nur private; public/unlisted, `publishAt`-Scheduling, Auto-Posting und Prozessneustart-Recovery bleiben offen.** | öffentliche/geplante Uploads + ggf. API-Audit |
| 3 | Instagram/TikTok nach offizieller Prüfung (App-Review/Audit, Hosting-Frage für IG klären) | Meta-/TikTok-Review bestanden |
| 4 | Scheduling/Queue (lokaler Worker verarbeitet `scheduled`-Drafts) | Phase 2 stabil |
| 5 | Analytics/Rückmeldung (Views/Likes zurück in ClipForge, Score-Feedback) | offizielle Analytics-APIs |

## 12. Grenzen (weiterhin gültig, Prompt 22 ändert daran nichts)

- Alle Drafts sind **rein lokal** — es gibt keine Server-Synchronisierung,
  keine Cloud, keine Datenbank.
- **Keine automatische Veröffentlichung.** Der Planner erzeugt Text/Metadaten
  und ein Pack für den manuellen Upload — kein Endpoint spricht mit
  YouTube/TikTok/Instagram.
- `scheduled_at` ist **nur ein gespeichertes Metadatum**, kein Hintergrund-Job.
  Es passiert nichts automatisch zum geplanten Zeitpunkt.
- Bevor in Phase 2/3 echte Uploads gebaut werden, müssen die jeweiligen
  Plattformregeln (Limits, Review-Prozesse, Quotas) **erneut anhand der dann
  aktuellen offiziellen Dokumentation geprüft werden** — die Angaben in §4
  sind ein Snapshot vom 2026-07-02.
