# Was ClipForge noch von dir braucht

Stand: ClipForge 2.0 (Branch `claude/creator-studio`). Preise sind Richtwerte
nach meiner Recherche (11/2026), **vor der Entscheidung beim Anbieter prüfen**.
Schlüssel gehören nur in **Studio → Einrichtung** (lokal `.env`, online
verschlüsselt je Benutzer) oder in die Secret-Einstellungen des Hosters —
**nie** in GitHub, Commits oder geteilte Dateien.

## 1. Kostenlos und ohne deine Mithilfe — fertig

| Was | Stand |
|---|---|
| Übergänge, Vorlagen, Lautstärke, Drag-and-drop | fertig, real getestet |
| Hintergrundentfernung Bild/Video (lokal) | fertig, real getestet (Modell lädst du per Klick) |
| B-Roll aus der eigenen Mediathek | fertig, real getestet |
| Videoübersetzung (Ablauf, Untertitel, Neuvertonung, Kennzeichnung) | fertig; „manuell“ kostenlos, lokal mit Argos-Modell (per Klick) |
| Avatar-Position, eigene Aufnahme je Szene | fertig, real getestet |
| Getrennte Benutzerbereiche, Rollen, Sitzungen | fertig, real getestet |
| Face-Swap-Schutz (Einwilligung, Gesichtsprüfung, Kennzeichnung) | fertig, real getestet |
| Backups, CI-Workflows | fertig (CI-Läufe auf GitHub noch nicht gesehen) |

## 2. Kostenlose Schlüssel (empfohlen)

| Schlüssel | Wozu | Wo |
|---|---|---|
| `PEXELS_API_KEY` | Stock-Videos/-Fotos für B-Roll | pexels.com/api |
| `PIXABAY_API_KEY` | Stock-Videos/-Fotos für B-Roll | pixabay.com/api/docs |
| `YOUTUBE_API_KEY` | YouTube-Trends (mostPopular) | console.cloud.google.com → YouTube Data API v3 |

## 3. Kostenpflichtige Schlüssel (optional)

| Schlüssel | Wozu | Kosten (Richtwert) | Kostenlose Alternative |
|---|---|---|---|
| `FAL_KEY` | KI-Video, Talking Avatar, Face Swap | Video ca. 0,05–0,30 USD/s, Avatar ca. 0,02–0,10 USD/s, Face Swap Bild ca. 0,05 USD | Motion, eigene Videos, Stock, Standbild-Avatar |
| `ELEVENLABS_API_KEY` | Premium-Stimmen, Stimmklon | Stimmklon ab bezahltem Tarif (ca. 5 USD/Monat) | Piper, eSpeak |
| `OPENAI_API_KEY` | Stimmen, KI-Bilder | Cent-Bereich je Szene | Piper, eigene Bilder |
| `ANTHROPIC_API_KEY` | Skripte, Übersetzung, Social-Texte | Cent-Bereich je Aufruf | lokale Skript-Gerüste, Argos, lokale Texte |

**Budget:** Die Projektbudgets in ClipForge reservieren Schätzwerte und
blockieren darüber — sie sind **keine** Ausgabengrenze beim Anbieter. Bitte
zusätzlich in jedem Anbieter-Konto ein Limit setzen.

## 4. Externe Konten und Plattform-Freigaben

| Plattform | Was du brauchst | Kosten | Stand in ClipForge |
|---|---|---|---|
| TikTok | Entwickler-App, Content Posting API; `video.upload` (Entwürfe), `video.publish` (Direct Post), optional `video.list` (Kennzahlen); **App-Audit** für öffentliche Posts | kostenlos | simuliert getestet; ohne Audit nur private Posts |
| Instagram | Business- oder Creator-Konto, Meta-App „Instagram API mit Instagram-Login“, Berechtigung `instagram_business_content_publish` (+ `…_manage_insights`), HTTPS-Redirect; App-Review für fremde Konten | kostenlos | simuliert getestet |
| X | Entwicklerkonto mit Nutzungsabrechnung, OAuth-2.0-App mit `tweet.write media.write offline.access` | nach Nutzung: Post ca. 0,015 USD, Video-Post laut Entwicklerberichten ca. 0,03 USD (in der X-Konsole prüfen) | simuliert getestet; Kostenbestätigung Pflicht |
| YouTube | Google-Cloud-Projekt (vorhanden) | kostenlos | privater Upload vorhanden, nicht mit echtem Konto getestet |

Redirect-URIs: `…/api/studio/accounts/<tiktok|instagram|x>/callback`
(lokal `http://127.0.0.1:8000`, Instagram verlangt HTTPS).

## 5. Hardware

| Was | Bedarf | Stand |
|---|---|---|
| Lokale KI-Videos (Wan, LTX-Video) | NVIDIA-GPU ab ~12 GB VRAM (Wan 14B: ~24 GB) | nicht eingebaut; ClipForge prüft deine Hardware und nennt Alternativen |
| Lokaler Talking Avatar / Lip-Sync | NVIDIA-GPU ab ~6 GB | nicht eingebaut (verfügbare Modelle meist nicht kommerziell lizenziert) |
| Hintergrundentfernung Video | läuft auf CPU, GPU nicht nötig | fertig; CPU langsam |

## 6. Deine Entscheidungen

1. **Freigabe für bezahlte Live-Tests** (fal.ai, ElevenLabs, OpenAI, Claude,
   X) mit Budgetgrenze, z. B. 2 USD gesamt.
2. **Plattform-Apps anlegen?** TikTok (inkl. Audit), Meta/Instagram, X.
   Ich kann die Einrichtung Schritt für Schritt begleiten.
3. **Hosting:** Railway, Render, Fly.io oder eigener VPS (Vergleich in
   `ONLINE_BETRIEB.md`). Kein kostenpflichtiges Deployment ohne dich.
4. **Face Swap online freischalten?** (`CLIPFORGE_FACE_SWAP_ONLINE=1`) —
   empfehle ich nur, wenn du die Nutzer kennst.
5. **Registrierung öffnen?** (`CLIPFORGE_REGISTRATION=open`) oder Konten nur
   durch dich anlegen.
6. **Datenbank:** JSON reicht für eine Instanz mit wenigen Nutzern; für
   größeren Betrieb Umstieg auf PostgreSQL (größerer Umbau).
7. **Piper-Lizenz:** `piper-tts` steht unter GPL-3.0 und wird nur als
   optionales Paket genutzt; bei kommerzieller Verteilung prüfen.
