#!/usr/bin/env bash
# Sicherung aller ClipForge-Daten (Konten, Projekte, Jobs, Schlüsseltresore).
#   deploy/backup.sh [Datenordner] [Zielordner] [Anzahl behalten]
# Im Container:  docker compose exec clipforge /app/deploy/backup.sh /data /data/backups 7
# Caches, Vorschauen und Modell-Downloads werden ausgelassen (wiederherstellbar).
# Die Tresore sind mit CLIPFORGE_SECRET_KEY verschlüsselt — diesen Schlüssel
# getrennt (z. B. im Passwortmanager) sichern, sonst ist das Backup unbrauchbar.
set -euo pipefail
DATA="${1:-${CLIPFORGE_DATA_DIR:-/data}}"
DEST="${2:-$DATA/backups}"
KEEP="${3:-7}"
mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/clipforge-$STAMP.tar.gz"
tar -czf "$OUT.part" -C "$DATA" \
  --exclude='./backups' --exclude='*/cache' --exclude='./models' --exclude='./piper' \
  --exclude='*/previews' --exclude='*.part' .
mv "$OUT.part" "$OUT"
chmod 600 "$OUT"
ls -1t "$DEST"/clipforge-*.tar.gz | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "[clipforge] Backup: $OUT"
