#!/usr/bin/env bash
# ClipForge — One-Command lokaler Start (Backend + Frontend).
#
# Startet FastAPI-Backend und Next.js-Frontend, wartet auf Healthchecks und
# beendet beide Prozesse sauber bei Ctrl+C (kein Zombie-Prozess). Erkennt
# belegte Ports und meldet klar, ob es sich um eine bereits laufende
# ClipForge-Instanz handelt oder um einen echten Konflikt.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/api"
WEB_DIR="$REPO_ROOT/web"

API_PORT="${CLIPFORGE_API_PORT:-8000}"
WEB_PORT="${CLIPFORGE_WEB_PORT:-3000}"
API_URL="http://127.0.0.1:${API_PORT}"
WEB_URL="http://127.0.0.1:${WEB_PORT}"

info()  { printf '\033[1;34m[start]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[start]\033[0m %s\n' "$1"; }
fail()  { printf '\033[1;31m[start]\033[0m %s\n' "$1" >&2; }

# .env sourcen, falls vorhanden (Backend liest ENV, kein eigenes dotenv-Loading).
if [ -f "$REPO_ROOT/.env" ]; then
  info "Lade $REPO_ROOT/.env …"
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

# Venv aus setup_local.sh bevorzugen, falls vorhanden.
if [ -x "$API_DIR/.venv/bin/python3" ]; then
  PYTHON_BIN="$API_DIR/.venv/bin/python3"
else
  PYTHON_BIN="python3"
fi

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3<&- 3>&-; return 0; }
  return 1
}

http_ok() {
  curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

API_PID=""
WEB_PID=""
STARTED_API=0
STARTED_WEB=0

cleanup() {
  trap - EXIT INT TERM
  # Nichts selbst gestartet (z.B. Port-Konflikt vor dem ersten Start) → still beenden.
  if [ "$STARTED_API" -eq 0 ] && [ "$STARTED_WEB" -eq 0 ]; then
    return
  fi
  echo
  info "Beende ClipForge …"
  for pid in "$API_PID" "$WEB_PID"; do
    if [ -n "$pid" ] && kill -0 "-$pid" 2>/dev/null; then
      kill -TERM "-$pid" 2>/dev/null || true
    fi
  done
  # Kurze Gnadenfrist, dann hart beenden falls nötig — keine Zombies.
  for _ in 1 2 3 4 5; do
    alive=0
    for pid in "$API_PID" "$WEB_PID"; do
      [ -n "$pid" ] && kill -0 "-$pid" 2>/dev/null && alive=1
    done
    [ "$alive" -eq 0 ] && break
    sleep 1
  done
  for pid in "$API_PID" "$WEB_PID"; do
    if [ -n "$pid" ] && kill -0 "-$pid" 2>/dev/null; then
      kill -KILL "-$pid" 2>/dev/null || true
    fi
  done
  ok "Gestoppt."
}
trap cleanup EXIT INT TERM

# --- Backend -------------------------------------------------------------------
# WICHTIG: Backend/Frontend werden als EINFACHE Kommandos direkt im Hauptskript
# backgrounded (kein "(...)"-Subshell, keine Command-Substitution) — sonst wäre
# "$!" ein Kind der Subshell statt dieses Skripts, und `wait` würde sofort mit
# "not a child of this shell" fehlschlagen (Skript würde sofort beenden statt
# auf Ctrl+C zu warten). `setsid` macht den Prozess gleichzeitig zum Leiter
# einer eigenen Prozessgruppe, sodass `kill -TERM "-$PID"` wirklich den
# gesamten Baum (inkl. ggf. gespawnter Kindprozesse) beendet — keine Zombies.
if port_in_use "$API_PORT"; then
  if http_ok "$API_URL/health"; then
    info "Backend-Port $API_PORT bereits belegt — antwortet auf /health, wird wiederverwendet."
  else
    fail "Backend-Port $API_PORT ist belegt, antwortet aber NICHT wie ClipForge-Backend."
    fail "Ein anderer Prozess blockiert den Port. Bitte freigeben oder CLIPFORGE_API_PORT setzen."
    exit 1
  fi
else
  info "Starte Backend auf $API_URL …"
  PYTHONPATH="$API_DIR" setsid "$PYTHON_BIN" -m uvicorn app:app --host 127.0.0.1 --port "$API_PORT" \
    >"$REPO_ROOT/.clipforge-backend.log" 2>&1 &
  API_PID=$!
  STARTED_API=1

  info "Warte auf Backend-Healthcheck …"
  for _ in $(seq 1 60); do
    http_ok "$API_URL/health" && break
    # Prozess schon tot (z.B. Startfehler)? Nicht die vollen 60s abwarten.
    kill -0 "$API_PID" 2>/dev/null || break
    sleep 1
  done
  if ! http_ok "$API_URL/health"; then
    fail "Backend ist nicht betriebsbereit geworden ($API_URL/health antwortet nicht)."
    fail "Log: $REPO_ROOT/.clipforge-backend.log"
    exit 1
  fi
  ok "Backend bereit ($API_URL)."
fi

# --- Frontend --------------------------------------------------------------------
# Der obige Block endet per `exit 1`, falls das Backend nicht startet — das
# Frontend wird also nie gestartet bzw. nie als betriebsbereit gemeldet, wenn
# das Backend nicht steht.
if port_in_use "$WEB_PORT"; then
  if http_ok "$WEB_URL"; then
    info "Frontend-Port $WEB_PORT bereits belegt — antwortet auf HTTP, wird wiederverwendet."
  else
    fail "Frontend-Port $WEB_PORT ist belegt, antwortet aber NICHT wie ein Next.js-Server."
    fail "Ein anderer Prozess blockiert den Port. Bitte freigeben oder CLIPFORGE_WEB_PORT setzen."
    exit 1
  fi
else
  info "Starte Frontend auf $WEB_URL …"
  NEXT_PUBLIC_API_BASE_URL="$API_URL" PORT="$WEB_PORT" setsid npm --prefix "$WEB_DIR" run dev \
    >"$REPO_ROOT/.clipforge-frontend.log" 2>&1 &
  WEB_PID=$!
  STARTED_WEB=1

  info "Warte auf Frontend …"
  for _ in $(seq 1 60); do
    http_ok "$WEB_URL" && break
    kill -0 "$WEB_PID" 2>/dev/null || break
    sleep 1
  done
  if ! http_ok "$WEB_URL"; then
    fail "Frontend antwortet nach 60s nicht auf $WEB_URL."
    fail "Log: $REPO_ROOT/.clipforge-frontend.log"
    exit 1
  fi
  ok "Frontend bereit ($WEB_URL)."
fi

echo
echo "─────────────────────────────────────────────"
echo " ClipForge läuft:"
echo
echo "   Backend:   $API_URL"
echo "   Frontend:  $WEB_URL"
echo
echo "   Öffnen:    $WEB_URL/upload"
echo "─────────────────────────────────────────────"
echo
info "Strg+C beendet beide Prozesse."

# Nur auf selbst gestartete Prozesse warten (wiederverwendete laufen unabhängig weiter).
WAIT_PIDS=()
[ "$STARTED_API" -eq 1 ] && WAIT_PIDS+=("$API_PID")
[ "$STARTED_WEB" -eq 1 ] && WAIT_PIDS+=("$WEB_PID")

if [ "${#WAIT_PIDS[@]}" -gt 0 ]; then
  # Wartet, bis EINER der beiden Prozesse endet (Crash) ODER Ctrl+C kommt;
  # der EXIT-Trap räumt in beiden Fällen den jeweils anderen Prozess mit auf.
  wait -n "${WAIT_PIDS[@]}"
else
  info "Beide Server liefen bereits — nichts zu verwalten. Beende dieses Skript (Server bleiben aktiv)."
fi
