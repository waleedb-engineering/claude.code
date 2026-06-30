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

---

## Seiten

| Pfad | Inhalt |
|---|---|
| `/` | Landing mit „Video hochladen" |
| `/upload` | Drop-Zone, Top-Clip-Anzahl, optionales Transkript-JSON |
| `/jobs` | Übersicht aller Jobs mit Live-Status |
| `/jobs/[jobId]` | Status + Progress/Logs, danach Clip-Karten + Downloads |

---

## Im Browser testen

1. <http://127.0.0.1:3000> öffnen → **Video hochladen**.
2. Ein Video wählen. Für einen schnellen, deterministischen Durchlauf ohne
   Whisper-Modell-Download zusätzlich das mitgelieferte Transkript als
   „Transkript (optional)" anhängen:
   - Video: `api/testdata/sample.mp4`
   - Transkript: `api/testdata/transcript.json`
3. **Analyse starten** → Weiterleitung zur Job-Seite; Fortschritt erscheint live.
4. Nach „Fertig" erscheinen die Clip-Karten mit Score, Aufschlüsselung,
   Begründung und Transkript-Ausschnitt.
5. **MP4 herunterladen** lädt den fertigen 9:16-Clip.

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

---

## Nicht enthalten (bewusst)

❌ Accounts · ❌ Billing · ❌ Cloud · ❌ Face-Tracking · ❌ Direkt-Posten auf
TikTok/Instagram/YouTube · ❌ neue Backend-Logik · ❌ Datenbank.
