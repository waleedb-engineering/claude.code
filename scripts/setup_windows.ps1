# ClipForge — Einrichtung unter Windows (PowerShell).
#
# Aufruf im ClipForge-Ordner:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#
# Installiert nichts systemweit ohne Rückfrage. Fehlende Programme werden mit
# dem passenden winget-Befehl gemeldet.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "api"
$Web = Join-Path $Root "web"

function Info($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[setup] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[setup] $m" -ForegroundColor Yellow }

$missing = @()
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $missing += "Python 3.13:  winget install Python.Python.3.13" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += "Node.js LTS:  winget install OpenJS.NodeJS.LTS" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  $missing += "FFmpeg:       winget install Gyan.FFmpeg"
}
if ($missing.Count -gt 0) {
  Warn "Folgende Programme fehlen. Installieren, PowerShell NEU öffnen, Skript erneut starten:"
  $missing | ForEach-Object { Warn "  $_" }
  exit 1
}

$venv = Join-Path $Api ".venv"
$python = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $python)) {
  Info "Erzeuge Python-Umgebung (api\.venv) mit Python 3.13 …"
  & py -3.13 -m venv $venv
  if ($LASTEXITCODE -ne 0) { Warn "Python 3.13 nicht gefunden: winget install Python.Python.3.13"; exit 1 }
}
Info "Installiere Backend-Pakete (dauert beim ersten Mal einige Minuten) …"
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $Api "requirements.txt")
if ($LASTEXITCODE -ne 0) { Warn "pip install fehlgeschlagen."; exit 1 }
Ok "Backend-Pakete installiert."

Info "Installiere Frontend-Pakete …"
Push-Location $Web
npm ci --silent
if ($LASTEXITCODE -ne 0) { Pop-Location; Warn "npm ci fehlgeschlagen."; exit 1 }
Pop-Location
Ok "Frontend-Pakete installiert."

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $Root ".env.example") $envFile
  Ok ".env aus .env.example erzeugt."
}

Info "Prüfe die Umgebung …"
& $python (Join-Path $Root "scripts\clipforge_doctor.py")
Ok "Fertig. Starten mit:  powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1"
