#!/usr/bin/env bash
# ClipForge — Release Check.
#
# Läuft VOR jedem Release-Candidate-Commit. Prüft Backend, Frontend, Security
# und Repo-Hygiene und gibt am Ende PASS/FAIL für den gesamten Release aus.
# Löst NIEMALS einen echten Google-Call oder echten Upload aus.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/api"
WEB_DIR="$REPO_ROOT/web"
LOG_DIR="$(mktemp -d)"

if [ -x "$API_DIR/.venv/bin/python3" ]; then
  PYTHON_BIN="$API_DIR/.venv/bin/python3"
else
  PYTHON_BIN="python3"
fi

PASS=0; WARN=0; FAIL=0
declare -a FAIL_NAMES=()

pass() { printf '\033[1;32m[PASS]\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
warn() { printf '\033[1;33m[WARN]\033[0m %s %s\n' "$1" "${2:-}"; WARN=$((WARN+1)); }
fail() {
  printf '\033[1;31m[FAIL]\033[0m %s %s\n' "$1" "${2:-}"
  FAIL=$((FAIL+1)); FAIL_NAMES+=("$1")
}
section() { printf '\n\033[1;34m── %s\033[0m\n' "$1"; }

run_logged() {
  # run_logged <label> <logfile> <cmd...>
  local label="$1" logfile="$2"; shift 2
  if "$@" >"$logfile" 2>&1; then
    pass "$label"
    return 0
  else
    fail "$label" "(Log: $logfile)"
    tail -12 "$logfile" | sed 's/^/    /'
    return 1
  fi
}

# ---------------------------------------------------------------------------
section "1) Git-Baum"
# ---------------------------------------------------------------------------
if [ -z "$(cd "$REPO_ROOT" && git status --porcelain)" ]; then
  pass "Git-Baum sauber (keine uncommitteten Änderungen)"
else
  warn "Git-Baum hat uncommittete Änderungen" "(vor dem finalen Release-Commit prüfen)"
fi

# ---------------------------------------------------------------------------
section "2) Environment Doctor"
# ---------------------------------------------------------------------------
if "$PYTHON_BIN" "$REPO_ROOT/scripts/clipforge_doctor.py" >"$LOG_DIR/doctor.log" 2>&1; then
  pass "Environment Doctor (keine FAIL-Prüfung)"
else
  fail "Environment Doctor meldet mindestens eine FAIL-Prüfung" "(Log: $LOG_DIR/doctor.log)"
  grep -E "FAIL" "$LOG_DIR/doctor.log" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
section "3) Backend-Tests"
# ---------------------------------------------------------------------------
cd "$API_DIR"
export PYTHONPATH="$API_DIR"

backend_pass=0; backend_fail=0
for t in tests/test_*.py; do
  name="$(basename "$t")"
  case "$name" in
    test_youtube_oauth.py|test_youtube_upload.py|test_youtube_recovery.py) continue ;;
  esac
  if "$PYTHON_BIN" "$t" >"$LOG_DIR/${name}.log" 2>&1; then
    backend_pass=$((backend_pass+1))
  else
    backend_fail=$((backend_fail+1))
    fail "Backend-Test $name" "(Log: $LOG_DIR/${name}.log)"
    tail -12 "$LOG_DIR/${name}.log" | sed 's/^/    /'
  fi
done
if [ "$backend_fail" -eq 0 ]; then
  pass "Backend-Tests ($backend_pass Dateien, ohne YouTube/Recovery — separat unten)"
fi

# ---------------------------------------------------------------------------
section "4) YouTube-Tests (OAuth + Upload, kein echter Google-Call)"
# ---------------------------------------------------------------------------
yt_ok=1
for t in test_youtube_oauth.py test_youtube_upload.py; do
  if "$PYTHON_BIN" "tests/$t" >"$LOG_DIR/${t}.log" 2>&1; then
    :
  else
    yt_ok=0
    fail "YouTube-Test $t" "(Log: $LOG_DIR/${t}.log)"
    tail -12 "$LOG_DIR/${t}.log" | sed 's/^/    /'
  fi
done
[ "$yt_ok" -eq 1 ] && pass "YouTube-Tests (test_youtube_oauth.py, test_youtube_upload.py)"

# ---------------------------------------------------------------------------
section "5) Recovery-/Race-Tests"
# ---------------------------------------------------------------------------
run_logged "Recovery-/Race-Tests (test_youtube_recovery.py)" \
  "$LOG_DIR/recovery.log" "$PYTHON_BIN" tests/test_youtube_recovery.py

# ---------------------------------------------------------------------------
section "6) CLI-Regression"
# ---------------------------------------------------------------------------
CLI_OUT="$(mktemp -d)"
if "$PYTHON_BIN" -m clipforge.cli testdata/sample.mp4 \
    --transcript testdata/transcript.json --out "$CLI_OUT" --top 2 \
    >"$LOG_DIR/cli.log" 2>&1; then
  pass "CLI-Regression (clipforge.cli, ohne Whisper via --transcript)"
else
  fail "CLI-Regression" "(Log: $LOG_DIR/cli.log)"
  tail -12 "$LOG_DIR/cli.log" | sed 's/^/    /'
fi
rm -rf "$CLI_OUT"

# ---------------------------------------------------------------------------
section "7) Frontend: TypeScript"
# ---------------------------------------------------------------------------
cd "$WEB_DIR"
run_logged "TypeScript-Typecheck (tsc --noEmit)" "$LOG_DIR/tsc.log" npx tsc --noEmit

# ---------------------------------------------------------------------------
section "8) Frontend: ESLint"
# ---------------------------------------------------------------------------
if npm run lint >"$LOG_DIR/eslint.log" 2>&1; then
  pass "ESLint (0 Fehler)"
else
  # Bekannte, dokumentierte Tech-Debt (3× react-hooks/set-state-in-effect,
  # siehe docs/KNOWN_ISSUES.md) — kein neuer Fund blockiert den Release,
  # aber jeder ANDERE Fehler tut es.
  known_errors=$(grep -c "react-hooks/set-state-in-effect" "$LOG_DIR/eslint.log" || true)
  total_errors=$(grep -oE "[0-9]+ problems? \([0-9]+ errors?" "$LOG_DIR/eslint.log" | grep -oE "[0-9]+ errors?" | grep -oE "^[0-9]+" || echo 0)
  if [ "${total_errors:-0}" -le "${known_errors:-0}" ] && [ "${known_errors:-0}" -gt 0 ]; then
    warn "ESLint: nur bekannte Tech-Debt-Fehler ($known_errors× set-state-in-effect)" "(dokumentiert in docs/KNOWN_ISSUES.md)"
  else
    fail "ESLint meldet unerwartete Fehler" "(Log: $LOG_DIR/eslint.log)"
    tail -20 "$LOG_DIR/eslint.log" | sed 's/^/    /'
  fi
fi

# ---------------------------------------------------------------------------
section "9) Frontend: next build"
# ---------------------------------------------------------------------------
run_logged "next build" "$LOG_DIR/build.log" npm run build

# ---------------------------------------------------------------------------
section "10) Playwright E2E"
# ---------------------------------------------------------------------------
run_logged "Playwright E2E-Suite" "$LOG_DIR/playwright.log" npx playwright test --reporter=line

# ---------------------------------------------------------------------------
section "11) Secret-Scan (Repo, staged + tracked)"
# ---------------------------------------------------------------------------
# Sucht nach Secret-WERTEN (bekannte Google-Token-Formate, oder ein
# Schlüsselname gefolgt von einem gequoteten String-Literal) — nicht nach
# bloßen Variablen-/Parameternamen wie `refresh_token=payload.get(...)`, die
# im Code ständig vorkommen. Test-Sentinels (Namenskonvention "SENTINEL" im
# gesamten Testsuite-Code für bewusst harmlose Platzhalter) werden explizit
# als solche erkannt und nicht als Fund gewertet.
cd "$REPO_ROOT"
SECRET_PATTERN='GOCSPX-[A-Za-z0-9_-]{6,}|ya29\.[A-Za-z0-9._-]{10,}|1//[0-9A-Za-z._-]{20,}|sk-ant-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|(access_token|refresh_token|id_token|client_secret)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9._/+-]{8,}["'"'"']|Bearer[[:space:]]+[A-Za-z0-9._-]{10,}'
raw_hits="$(git grep -nIE "$SECRET_PATTERN" -- . ':!scripts/release_check.sh' ':!web/e2e/helpers/youtube.ts' 2>/dev/null || true)"
# Zeilen mit dem etablierten Test-Sentinel-Marker herausfiltern (case-insensitive).
hits="$(printf '%s\n' "$raw_hits" | grep -viE "sentinel" || true)"
if [ -z "$hits" ]; then
  pass "Secret-Scan Repo: keine Treffer außerhalb Scanner-Patterndefinitionen/Test-Sentinels"
else
  fail "Secret-Scan Repo: möglicher Treffer" ""
  echo "$hits" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
section "12) .env nicht committed"
# ---------------------------------------------------------------------------
if git ls-files | grep -qE '(^|/)\.env$|(^|/)\.env\.local$'; then
  fail ".env/.env.local ist im Git-Index (darf nie committet werden)"
else
  pass ".env/.env.local nicht getrackt"
fi

# ---------------------------------------------------------------------------
section "13) Keine test-results/Playwright-Reports committed"
# ---------------------------------------------------------------------------
if git ls-files | grep -qE '(^|/)(test-results|playwright-report|blob-report)/'; then
  fail "test-results/playwright-report im Git-Index"
else
  pass "Keine Playwright-Artefakte getrackt"
fi

# ---------------------------------------------------------------------------
section "14) Keine Videos/Screenshots/Traces committed"
# ---------------------------------------------------------------------------
media_hits="$(git ls-files | grep -iE '\.(mp4|mov|mkv|webm|avi|m4v|png|jpe?g|zip|trace)$' || true)"
if [ -z "$media_hits" ]; then
  pass "Keine Video-/Bild-/Zip-/Trace-Dateien im Git-Index"
else
  fail "Medien-/Artefakt-Dateien im Git-Index gefunden"
  echo "$media_hits" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
section "Zusammenfassung"
# ---------------------------------------------------------------------------
echo
echo "PASS=$PASS  WARN=$WARN  FAIL=$FAIL"

if [ "$FAIL" -eq 0 ]; then
  rm -rf "$LOG_DIR"
  echo
  echo "RELEASE CHECK PASSED"
  exit 0
else
  echo
  echo "Logs erhalten unter: $LOG_DIR"
  echo "RELEASE CHECK FAILED (${FAIL_NAMES[*]})"
  exit 1
fi
