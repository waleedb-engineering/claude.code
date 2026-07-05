#!/usr/bin/env bash
# ClipForge — One-Command lokales Setup.
#
# Installiert Backend- und Frontend-Abhängigkeiten, legt Verzeichnisse an und
# erzeugt fehlende .env-Dateien aus den *.example-Vorlagen. Überschreibt NIE
# eine bestehende .env/.env.local. Generiert keine Secrets. Installiert ffmpeg
# nicht heimlich systemweit — es wird nur geprüft.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/api"
WEB_DIR="$REPO_ROOT/web"

info()  { printf '\033[1;34m[setup]\033[0m %s\n' "$1"; }
warn()  { printf '\033[1;33m[setup]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[setup]\033[0m %s\n' "$1"; }

cd "$REPO_ROOT"

# --- 1) Python venv (nur wenn sinnvoll: keine bereits aktive venv/conda) ----
if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_PREFIX:-}" ]; then
  info "Aktive Python-Umgebung erkannt ($( [ -n "${VIRTUAL_ENV:-}" ] && echo "venv: $VIRTUAL_ENV" || echo "conda: $CONDA_PREFIX")) — verwende diese, kein eigenes venv."
  PYTHON_BIN="python3"
elif [ -d "$API_DIR/.venv" ]; then
  info "Vorhandenes venv gefunden (api/.venv) — verwende es."
  # shellcheck disable=SC1091
  source "$API_DIR/.venv/bin/activate"
  PYTHON_BIN="python3"
else
  info "Erzeuge neues venv unter api/.venv …"
  python3 -m venv "$API_DIR/.venv"
  # shellcheck disable=SC1091
  source "$API_DIR/.venv/bin/activate"
  PYTHON_BIN="python3"
  ok "venv aktiviert."
fi

# --- 2) Backend-Requirements -------------------------------------------------
info "Installiere Backend-Requirements (api/requirements.txt) …"
"$PYTHON_BIN" -m pip install --quiet --upgrade pip
"$PYTHON_BIN" -m pip install --quiet -r "$API_DIR/requirements.txt"
ok "Backend-Requirements installiert."

# --- 3) Frontend npm install --------------------------------------------------
info "Installiere Frontend-Dependencies (web/) …"
(cd "$WEB_DIR" && npm install --silent)
ok "Frontend-Dependencies installiert."

# --- 4) Verzeichnisse anlegen -------------------------------------------------
mkdir -p "$API_DIR/jobs" "$API_DIR/config"
ok "Verzeichnisse api/jobs, api/config vorhanden."

# --- 5) .env aus .env.example erzeugen — NIE eine bestehende Datei anfassen --
copy_if_missing() {
  local example="$1" target="$2"
  if [ -f "$target" ]; then
    info "$target existiert bereits — unverändert gelassen."
  elif [ -f "$example" ]; then
    cp "$example" "$target"
    ok "$target aus $(basename "$example") erzeugt."
  fi
}
copy_if_missing "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
copy_if_missing "$WEB_DIR/.env.example" "$WEB_DIR/.env.local"

# --- 6) ffmpeg/ffprobe nur prüfen, nicht installieren ------------------------
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  ok "ffmpeg/ffprobe gefunden."
else
  warn "ffmpeg/ffprobe NICHT gefunden. Bitte manuell installieren (z.B. 'apt install ffmpeg' /"
  warn "'brew install ffmpeg') — wird NICHT automatisch systemweit installiert."
fi

# --- 7) Doctor ausführen ------------------------------------------------------
echo
info "Führe Environment Doctor aus …"
"$PYTHON_BIN" "$REPO_ROOT/scripts/clipforge_doctor.py" || true

# --- 8) Nächste Schritte -------------------------------------------------------
echo
ok "Setup abgeschlossen."
cat <<'EOF'

Nächste Schritte:
  1. ClipForge starten:      ./scripts/start_local.sh
  2. Browser öffnen:         http://127.0.0.1:3000/upload
  3. Testflow:                siehe docs/LOCAL_BETA_GUIDE.md
EOF
