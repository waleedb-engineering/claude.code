# Was ClipForge noch von dir braucht

Alle Preise sind Richtwerte nach meinem Kenntnisstand (die Anbieterseiten
waren aus der Entwicklungsumgebung nicht erreichbar) — **vor der Entscheidung
beim Anbieter prüfen**. Schlüssel gehören nur in **Studio → Einrichtung**
(lokal: `.env`, online: verschlüsselt) oder in die Secret-Einstellungen des
Hosting-Anbieters — **nie** in GitHub, Commits oder geteilte Dateien.

## 1. Kostenlos, ohne deine Mithilfe — erledigt

| Was | Stand |
|---|---|
| Lokale Stimme auf Windows/macOS/Linux (eSpeak NG über pip) | fertig, getestet |
| Windows-Start (PowerShell-Skripte, Pfade, `.env`) | fertig; auf echtem Windows **nicht** getestet |
| Benutzeranmeldung, Docker-Vorbereitung | fertig, getestet (Docker-Image nicht gebaut) |
| YouTube-Import für eigene Videos | fertig, getestet |

## 2. Braucht einen API-Schlüssel (kostenpflichtig)

| Was | Wozu | Wo | Kosten (Richtwert) | Kostenlose Alternative | Arbeit bis dahin möglich? |
|---|---|---|---|---|---|
| `FAL_KEY` | KI-Video (Text/Bild→Video) und Talking Avatar | fal.ai → Dashboard → Keys | KI-Video ca. 0,05–0,30 USD je Sekunde (modellabhängig), Avatar ca. 0,02–0,10 USD je Sekunde | keine gleichwertige; lokal nur Motion-Hintergründe, eigene Videos, Ken-Burns-Bilder | ja — Adapter fertig, nur der Live-Test fehlt |
| `ELEVENLABS_API_KEY` | Premium-Stimmen, **Stimmklon** | elevenlabs.io → Profil → API Keys | Stimmen nach Zeichen (ca. 0,15–0,30 USD/1000 Zeichen); Stimmklon braucht einen bezahlten Tarif (ab ca. 5 USD/Monat) | Piper (lokal, gut), eSpeak (lokal, synthetisch) | ja |
| `OPENAI_API_KEY` | Stimmen (TTS), KI-Bilder | platform.openai.com → API keys | TTS ca. 0,015 USD/1000 Zeichen, Bild ca. 0,04–0,08 USD | Piper/eSpeak; eigene Bilder | ja |
| `ANTHROPIC_API_KEY` | ausformulierte Skripte aus Prompts, Ziel/Zielgruppe/Hinweise | console.anthropic.com | nach Tokens, meist Cent-Bereich je Skript | lokale Zusammenfassung/Gerüst | ja |

**Live-Tests:** Jeder echte Aufruf kostet Geld. Ich mache sie erst nach deiner
ausdrücklichen Freigabe, mit kleinem Projektbudget (z. B. 1 USD).
Voraussetzung ist außerdem, dass die Entwicklungsumgebung diese Hosts
erreichen darf (aktuell gesperrt) — oder du testest lokal.

## 3. Braucht externe Konten oder Plattform-Freigaben

| Was | Wozu | Wo | Kosten | Stand |
|---|---|---|---|---|
| TikTok-Entwickler-App mit Content Posting API (`video.upload`), dann `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` | Upload in deine TikTok-Entwürfe | developers.tiktok.com | kostenlos | Adapter fertig, **ungetestet** live; Redirect-URI in der App eintragen: `http://127.0.0.1:8000/api/studio/accounts/tiktok/callback` |
| TikTok App-Audit | direktes **öffentliches** Posten ohne Umweg über die App | TikTok-Prüfprozess | kostenlos, dauert | nicht umgesetzt (bewusst: Entwürfe-Weg reicht und hält dich in Kontrolle) |
| Meta-App + Instagram Business/Creator-Konto + App-Review (`instagram_business_content_publish`) | Instagram Reels direkt | developers.facebook.com | kostenlos | **kein Adapter**; zusätzlich braucht Instagram eine öffentlich erreichbare Video-URL (passt erst zum Online-Betrieb) |
| X-Developer-Konto mit Schreibzugriff | Posten auf X | developer.x.com | kostenpflichtiger Zugang (Basic, Richtwert um 200 USD/Monat) | **kein Adapter** — Entscheidung, ob dir das den Preis wert ist |
| Google-Cloud-Projekt mit YouTube Data API (bereits vorhanden) | privater YouTube-Upload | console.cloud.google.com | kostenlos | vorhanden, weiterhin **nicht** mit echtem Konto getestet |

Bis dahin gilt für alle Plattformen: Export-Pack herunterladen und selbst posten.

## 4. Braucht zusätzliche Hardware / GPU

| Was | Bedarf | Stand |
|---|---|---|
| Lokales KI-Video (z. B. Wan, LTX-Video) | NVIDIA-GPU mit 12–24 GB VRAM, Modelle 10–30 GB | nicht umgesetzt — auf normalen Laptops nicht sinnvoll |
| Lokaler Talking Avatar (SadTalker, Wav2Lip) | NVIDIA-GPU ab ~6 GB VRAM; CPU-only sehr langsam (Minuten je Sekunde Video) | nicht umgesetzt; Cloud-Weg über fal.ai vorhanden |
| Lokale Transkription (Whisper) | läuft auf CPU, GPU beschleunigt | vorhanden |

## 5. Braucht eine Entscheidung von dir

1. **Hosting-Anbieter** (Railway, Render, Fly.io oder eigener Server) und
   Größe (mind. 2 GB RAM). Vergleich: `docs/ONLINE_BETRIEB.md`.
2. **Face Swap — umsetzen ja/nein?** Ich habe es bewusst **nicht** gebaut.
   Gründe: Lokale Modelle (z. B. inswapper) sind nicht für kommerzielle
   Nutzung lizenziert und in der Umgebung nicht ladbar; vor allem ist ein
   bloßes „Ich bestätige“ kein wirksamer Schutz gegen Deepfakes fremder
   Personen. Wenn du es willst, würde ich es nur so bauen:
   - Gesicht nur von einem **verifizierten Referenzfoto deines Kontos**
     (Abgleich per Gesichtsmerkmalen, fremde Gesichter werden abgelehnt),
   - **sichtbare Kennzeichnung** „KI-verändert“ im Export, nicht abschaltbar,
   - Protokoll jeder Nutzung, Cloud-Anbieter mit eigener Missbrauchsprüfung.
   Kosten: Cloud ca. 0,01–0,05 USD je Bild, Video deutlich mehr.
3. **X-API-Zugang** — lohnt sich der Monatspreis für dich?
4. **Getrennte Bereiche pro Benutzer** im Online-Betrieb — nur nötig, wenn
   andere als du und Vertraute ClipForge nutzen sollen (größerer Umbau).
5. **Freigabe für bezahlte Live-Tests** der Cloud-Adapter (fal.ai,
   ElevenLabs, OpenAI, TikTok), mit Budgetgrenze.
