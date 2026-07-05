#!/usr/bin/env bash
# ClipForge — Beta-Package bauen.
#
# Erzeugt ein reproduzierbares, secret-freies Distributions-Tarball unter
# dist/clipforge-beta-<VERSION>.tar.gz. Enthält GENAU die Dateien, die auch in
# einem sauberen Commit landen würden (getrackt + untracked-aber-nicht-
# ignoriert) — .gitignore-Regeln (node_modules, .venv, .next, api/jobs, .env,
# test-results, *.mp4, …) greifen dadurch automatisch. Zusätzlich ein
# expliziter Sicherheitsfilter als zweite Verteidigungslinie.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
PKG_NAME="clipforge-beta-${VERSION}"
DIST_DIR="$REPO_ROOT/dist"
STAGE_DIR="$(mktemp -d)"
TARGET_DIR="$STAGE_DIR/$PKG_NAME"

info()  { printf '\033[1;34m[package]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[package]\033[0m %s\n' "$1"; }
fail()  { printf '\033[1;31m[package]\033[0m %s\n' "$1" >&2; }

cd "$REPO_ROOT"
mkdir -p "$DIST_DIR" "$TARGET_DIR"

info "Ermittle Dateiliste (getrackt + untracked-aber-nicht-ignoriert) …"
# Exakt die Dateien, die bei "git add -A && git commit" jetzt landen würden.
mapfile -t FILES < <(
  { git ls-files; git ls-files --others --exclude-standard; } | sort -u
)

# Zweite Verteidigungslinie: explizite Verbotsliste, auch falls versehentlich
# etwas Gefährliches getrackt wäre. Secrets/Credentials/Keychain/Medien/
# Build-Artefakte dürfen NIE ins Package, unabhängig vom Git-Zustand.
is_forbidden() {
  case "$1" in
    .env|.env.*|*/.env|*/.env.*) [ "$(basename "$1")" = ".env.example" ] && return 1; return 0 ;;
    *.mp4|*.mov|*.mkv|*.webm|*.avi|*.m4v|*.wav|*.mp3) return 0 ;;
    *.png|*.jpg|*.jpeg|*.zip|*.trace) return 0 ;;
    api/jobs/*|*/api/jobs/*) return 0 ;;
    api/config/*|*/api/config/*) return 0 ;;
    *node_modules/*|*.venv/*|*/.next/*|*test-results/*|*playwright-report/*|*blob-report/*) return 0 ;;
    *credentials*|*keychain*|*token*.json) return 0 ;;
    .git|.git/*) return 0 ;;
    *) return 1 ;;
  esac
}

copied=0
skipped=0
for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  if is_forbidden "$f"; then
    skipped=$((skipped+1))
    continue
  fi
  mkdir -p "$TARGET_DIR/$(dirname "$f")"
  cp "$f" "$TARGET_DIR/$f"
  copied=$((copied+1))
done
info "Kopiert: $copied Dateien · gefiltert/ausgeschlossen: $skipped"

# VERSION/CHANGELOG/README/requirements/package.json sind über die
# Dateiliste bereits enthalten (sie sind getrackt) — keine Sonderbehandlung
# nötig. Sicherstellen, dass die Kern-Dateien wirklich da sind:
for must in VERSION CHANGELOG.md README.md .env.example api/requirements.txt web/package.json scripts/setup_local.sh scripts/start_local.sh scripts/clipforge_doctor.py; do
  if [ ! -f "$TARGET_DIR/$must" ]; then
    fail "Erwartete Datei fehlt im Package: $must"
    rm -rf "$STAGE_DIR"
    exit 1
  fi
done
ok "Kern-Dateien vorhanden (VERSION, CHANGELOG, README, .env.example, requirements, package.json, scripts/)."

TARBALL="$DIST_DIR/${PKG_NAME}.tar.gz"
info "Baue Tarball: $TARBALL …"
tar -czf "$TARBALL" -C "$STAGE_DIR" "$PKG_NAME"
rm -rf "$STAGE_DIR"

size_h="$(du -h "$TARBALL" | cut -f1)"
ok "Fertig: $TARBALL ($size_h, $copied Dateien)"
echo "$TARBALL"
