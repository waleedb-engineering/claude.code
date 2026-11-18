# ClipForge installieren und starten

ClipForge läuft lokal auf Windows, macOS und Linux. Benötigt werden Git,
Python 3.13 (3.11+ funktioniert, für Windows bitte 3.13), Node.js LTS und
FFmpeg. Alles Weitere installieren die Skripte.

Nach dem Start: **http://127.0.0.1:3000/studio**

Stimme ohne API-Schlüssel: Auf allen Systemen ist eSpeak NG (über pip, keine
Installation nötig) dabei; zusätzlich werden die Windows-Systemstimmen bzw.
die macOS-Stimme `say` erkannt. Bessere lokale Qualität bietet optional Piper
(siehe unten).

## Windows

In **PowerShell**:

1. Programme installieren, danach PowerShell schließen und neu öffnen:

   ```powershell
   winget install Git.Git Python.Python.3.13 OpenJS.NodeJS.LTS Gyan.FFmpeg
   ```

2. Code holen:

   ```powershell
   git clone -b claude/creator-studio https://github.com/waleedb-engineering/claude.code ClipForge
   ```

3. Einrichten:

   ```powershell
   cd ClipForge
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
   ```

4. Starten (öffnet zwei Fenster und den Browser):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
   ```

Beenden: die beiden Fenster schließen.

Hinweise:
- `-ExecutionPolicy Bypass` gilt nur für diesen einen Aufruf und ändert keine
  Systemeinstellung.
- Weitere Windows-Stimmen: Einstellungen → Zeit und Sprache → Sprache →
  Sprachpaket mit „Sprachausgabe“ hinzufügen.
- Die `.env` liest das Backend unter Windows selbst ein.

## macOS

1. Programme (mit [Homebrew](https://brew.sh)):

   ```bash
   brew install git python@3.13 node ffmpeg
   ```

2. Code holen und einrichten:

   ```bash
   git clone -b claude/creator-studio https://github.com/waleedb-engineering/claude.code ClipForge
   ```

   ```bash
   cd ClipForge && ./scripts/setup_local.sh
   ```

3. Starten:

   ```bash
   ./scripts/start_local.sh
   ```

## Linux (Debian/Ubuntu)

1. Programme:

   ```bash
   sudo apt install git python3 python3-venv nodejs npm ffmpeg
   ```

   Node.js muss Version 20 oder neuer sein (`node --version`); sonst von
   nodejs.org installieren.

2. Code holen, einrichten, starten:

   ```bash
   git clone -b claude/creator-studio https://github.com/waleedb-engineering/claude.code ClipForge
   ```

   ```bash
   cd ClipForge && ./scripts/setup_local.sh
   ```

   ```bash
   ./scripts/start_local.sh
   ```

## Optional: bessere lokale Stimmen mit Piper

Piper erzeugt deutlich natürlichere Stimmen, lokal und kostenlos.

```bash
api/.venv/bin/python -m pip install piper-tts
```

```bash
api/.venv/bin/python -m piper.download_voices de_DE-thorsten-medium en_US-lessac-medium --data-dir api/studio_data/piper
```

Unter Windows heißt der Python-Pfad `api\.venv\Scripts\python.exe`. Danach
erscheint „Piper“ unter **Studio → Einrichtung** als bereit.

## Prüfen

```bash
api/.venv/bin/python scripts/clipforge_doctor.py
```

Zeigt, was fehlt, mit dem passenden Installationsbefehl für dein System.

## Typische Probleme

| Meldung | Lösung |
|---|---|
| `ffmpeg wurde nicht gefunden` | FFmpeg installieren (siehe oben) und das Terminal **neu öffnen** |
| `Port 8000 ist belegt` | Läuft ClipForge schon? Sonst das andere Programm beenden |
| Video ohne Stimme | In **Studio → Einrichtung** prüfen, ob „eSpeak NG“ bereit ist; sonst Einrichtung erneut ausführen |
| `py -3.13` nicht gefunden (Windows) | `winget install Python.Python.3.13`, PowerShell neu öffnen |
