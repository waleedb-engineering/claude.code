#!/usr/bin/env bash
# Startet Backend (intern, 127.0.0.1:8000) und Oberfläche (öffentlich, $PORT).
# Stirbt einer der beiden Prozesse, beendet sich der Container → die Plattform
# startet ihn neu; unterbrochene Aufgaben werden beim Start wiederhergestellt.
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
DATA="${CLIPFORGE_DATA_DIR:-/data}"
PORT="${PORT:-3000}"
mkdir -p "$DATA"

export CLIPFORGE_STUDIO_DIR="${CLIPFORGE_STUDIO_DIR:-$DATA/studio}"
export CLIPFORGE_JOBS_DIR="${CLIPFORGE_JOBS_DIR:-$DATA/jobs}"
export CLIPFORGE_AUTH_DIR="${CLIPFORGE_AUTH_DIR:-$DATA/auth}"
export CLIPFORGE_API_TOKEN_FILE="${CLIPFORGE_API_TOKEN_FILE:-$DATA/api_token}"
export CLIPFORGE_ENV_FILE="${CLIPFORGE_ENV_FILE:-$DATA/clipforge.env}"
export CLIPFORGE_BRAND_KIT="${CLIPFORGE_BRAND_KIT:-$DATA/brand_kit.json}"
export CLIPFORGE_PIPER_VOICES="${CLIPFORGE_PIPER_VOICES:-$DATA/piper}"
export CLIPFORGE_API_INTERNAL_URL="http://127.0.0.1:8000"

if [ "${CLIPFORGE_AUTH:-local}" = "accounts" ]; then
  KEY="${CLIPFORGE_SECRET_KEY:-}"
  if [ "${#KEY}" -lt 32 ]; then
    echo "[clipforge] FEHLER: CLIPFORGE_SECRET_KEY (mind. 32 Zeichen) muss gesetzt sein." >&2
    echo "[clipforge] Erzeugen z. B. mit: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'" >&2
    exit 1
  fi
  if ! (cd "$APP_DIR/api" && python -m clipforge.auth list-users) 2>/dev/null | grep -q .; then
    if [ -n "${CLIPFORGE_ADMIN_USER:-}" ] && [ -n "${CLIPFORGE_ADMIN_PASSWORD:-}" ]; then
      (cd "$APP_DIR/api" && CLIPFORGE_NEW_PASSWORD="$CLIPFORGE_ADMIN_PASSWORD" \
        python -m clipforge.auth create-user "$CLIPFORGE_ADMIN_USER")
      echo "[clipforge] Erstes Konto angelegt. CLIPFORGE_ADMIN_PASSWORD jetzt aus der Konfiguration entfernen."
    else
      echo "[clipforge] Noch kein Konto. Einmalig CLIPFORGE_ADMIN_USER und CLIPFORGE_ADMIN_PASSWORD setzen" >&2
      echo "[clipforge] oder im Container: cd /app/api && python -m clipforge.auth create-user <name>" >&2
    fi
  fi
fi

cd "$APP_DIR/api"
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log &
BACKEND=$!
cd "$APP_DIR/web"
node node_modules/next/dist/bin/next start -p "$PORT" -H 0.0.0.0 &
FRONTEND=$!

trap 'kill -TERM $BACKEND $FRONTEND 2>/dev/null; wait' TERM INT
wait -n $BACKEND $FRONTEND
STATUS=$?
echo "[clipforge] Ein Prozess wurde beendet (Status $STATUS) — Container stoppt." >&2
kill -TERM $BACKEND $FRONTEND 2>/dev/null || true
wait || true
exit "$STATUS"
