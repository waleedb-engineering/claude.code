#!/usr/bin/env bash
# Erzeugt lokal ein kleines, deterministisches Test-Video (60s, Ton + Bild),
# falls du kein eigenes Video zur Hand hast. Nutzt ffmpeg (muss installiert
# sein). Erzeugt NICHTS im Repo-Git — die Ausgabe liegt unter api/testdata/
# und ist dort per .gitignore ausgeschlossen (*.mp4 wird nie committet).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/api/testdata/sample.mp4}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg nicht gefunden — bitte zuerst installieren (siehe docs/LOCAL_BETA_GUIDE.md)." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=25:duration=60 \
       -f lavfi -i sine=frequency=320:duration=60 \
       -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$OUT"

echo "Fertig: $OUT"
echo "Zum schnellen, deterministischen Test (ohne Whisper-Download) zusätzlich"
echo "api/testdata/transcript.json beim Upload als Transkript mitgeben."
