# ClipForge — Start unter Windows (PowerShell).
#
# Aufruf im ClipForge-Ordner:
#   powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
#
# Startet Backend (Port 8000) und Oberfläche (Port 3000) in eigenen Fenstern
# und öffnet den Browser. Beenden: die beiden Fenster schließen.
# Das Backend lädt die .env selbst (kein "source" unter Windows nötig).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "api"
$Web = Join-Path $Root "web"
$python = Join-Path $Api ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Noch nicht eingerichtet. Zuerst: powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1" -ForegroundColor Yellow
  exit 1
}
foreach ($port in 8000, 3000) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port $port ist belegt. Läuft ClipForge schon? Sonst das Programm auf Port $port beenden." -ForegroundColor Yellow
    exit 1
  }
}

Start-Process -FilePath $python -WorkingDirectory $Api `
  -ArgumentList "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"
Start-Process -FilePath "cmd.exe" -WorkingDirectory $Web -ArgumentList "/k", "npm run dev"

Write-Host "Warte auf ClipForge …" -ForegroundColor Cyan
for ($i = 0; $i -lt 90; $i++) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3000/studio" -TimeoutSec 2 | Out-Null
    break
  } catch { Start-Sleep -Seconds 1 }
}
Start-Process "http://127.0.0.1:3000/studio"
Write-Host "ClipForge läuft: http://127.0.0.1:3000/studio" -ForegroundColor Green
