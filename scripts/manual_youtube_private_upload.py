#!/usr/bin/env python3
"""Sicherer MANUELLER echter Private-Upload-Test (Phase 3b).

Dieses Skript ist der EINZIGE Weg, einen echten YouTube-Upload auszulösen —
und nur, wenn ein Mensch es bewusst startet UND alle Voraussetzungen erfüllt
sind. **Automatische Tests importieren/rufen dieses Skript nie** und setzen das
Real-Test-Flag nie.

Voraussetzungen (ALLE nötig, sonst „REAL TEST NOT RUN"):
  - CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true
  - CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST=true
  - OAuth ready (Flag + client_secrets vorhanden)
  - Token im Keychain vorhanden (keyring verfügbar)
  - Draft validiert, MP4 vorhanden
  - platform=youtube_shorts, privacy_status=private
  - interaktive Bestätigung: exakt `UPLOAD_PRIVATE`

Es wird NUR privat hochgeladen, nichts automatisch gelöscht, nichts öffentlich
geschaltet. Am Ende: manuelle Prüfanleitung fürs YouTube Studio.

Aufruf (aus dem Repo-Root):
    CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST=true \
    CLIPFORGE_YOUTUBE_CLIENT_SECRETS=/pfad/client_secrets.json \
    python scripts/manual_youtube_private_upload.py <job_id> <publishing_id>

Exit-Codes: 0 = echter Upload ausgeführt (Ergebnis anzeigen); 2 = REAL TEST
NOT RUN (Voraussetzung fehlt / abgebrochen). Es wird NIE ein Erfolg behauptet,
wenn kein echter Upload stattfand.
"""

from __future__ import annotations

import os
import sys

# Repo-Layout: api/ auf den Pfad legen.
_HERE = os.path.dirname(os.path.abspath(__file__))
_API = os.path.join(os.path.dirname(_HERE), "api")
sys.path.insert(0, _API)

from clipforge.config import get_settings  # noqa: E402
from clipforge.platforms.youtube_upload import YouTubeUploadService  # noqa: E402
from clipforge.publishing import load_draft  # noqa: E402

_NOT_RUN = "REAL TEST NOT RUN"


def _abort(reason: str) -> int:
    print(f"\n{_NOT_RUN}: {reason}")
    print("Es wurde KEIN echter Upload ausgeführt.")
    return 2


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python scripts/manual_youtube_private_upload.py "
              "<job_id> <publishing_id>")
        return _abort("Argumente fehlen (job_id, publishing_id)")
    job_id, publishing_id = argv[1], argv[2]

    settings = get_settings()

    # 1) Harte Flag-Gates (früh, ohne irgendetwas zu tun).
    if not settings.enable_youtube_upload:
        return _abort("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD ist nicht true")
    if not settings.enable_youtube_real_test:
        return _abort("CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST ist nicht true")

    jobs_dir = os.environ.get(
        "CLIPFORGE_JOBS_DIR", os.path.join(_API, "jobs"))
    job_dir = os.path.join(jobs_dir, job_id)
    if not os.path.isdir(job_dir):
        return _abort(f"Job-Ordner nicht gefunden: {job_id}")

    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        return _abort(f"Draft nicht gefunden: {publishing_id}")
    if draft.get("platform") != "youtube_shorts":
        return _abort("Draft ist nicht für youtube_shorts")

    svc = YouTubeUploadService(settings)

    # 2) Alle weiteren Voraussetzungen (OAuth/Token/Keyring/Draft/MP4).
    ready, reasons = svc.real_test_ready(draft)
    if not ready:
        return _abort("Voraussetzungen fehlen: " + ", ".join(sorted(set(reasons))))

    # 3) Draft/Video anzeigen.
    print("=" * 64)
    print("ECHTER PRIVATER YouTube-Upload — manueller Test")
    print("=" * 64)
    print(f"  job_id:        {job_id}")
    print(f"  publishing_id: {publishing_id}")
    print(f"  Titel:         {draft.get('title')!r}")
    print(f"  MP4:           {os.path.basename(draft.get('mp4_path') or '')}")
    print(f"  privacy:       private (fest — kein public/unlisted)")
    us = svc.upload_status(draft)
    print(f"  idempotency:   {us['idempotency_state']}  "
          f"(attempts: {us['publish_attempt_count']})")
    if not us["can_retry"] and us["idempotency_state"] != "never_attempted":
        return _abort(f"Idempotenz-Zustand erlaubt keinen Upload "
                      f"({us['idempotency_state']}) — ggf. Studio prüfen")

    # 4) Interaktive Doppel-Bestätigung.
    print("\nDies lädt das Video WIRKLICH (privat) in dein YouTube-Konto hoch.")
    try:
        typed = input("Zum Bestätigen exakt 'UPLOAD_PRIVATE' eingeben: ").strip()
    except (EOFError, KeyboardInterrupt):
        return _abort("keine Bestätigung (Abbruch)")
    if typed != "UPLOAD_PRIVATE":
        return _abort("Bestätigung war nicht exakt 'UPLOAD_PRIVATE'")

    # 5) Echter privater Upload.
    print("\nStarte echten privaten Upload …")
    result = svc.upload_private(
        job_dir, publishing_id, draft,
        confirm="UPLOAD_PRIVATE", privacy_status="private",
    )

    print("-" * 64)
    if result.get("success"):
        vid = result.get("external_post_id")
        print("✓ ECHTER UPLOAD ERFOLGREICH (privat).")
        print(f"  external_post_id (Video-ID): {vid}")
        print(f"  Status: {result.get('status')} · privacy: private")
        print("\nManuelle Prüfung:")
        print("  1) https://studio.youtube.com öffnen → 'Inhalte'.")
        print(f"  2) Das Video mit ID {vid} sollte als 'Privat' erscheinen.")
        print("  3) Es ist NUR für dich sichtbar. Es wird NICHTS automatisch")
        print("     öffentlich geschaltet oder gelöscht.")
        return 0

    # Kein eindeutiger Erfolg → NIE als Erfolg ausgeben.
    code = result.get("error_code")
    if result.get("idempotency_state") == "uncertain":
        print(f"{_NOT_RUN} (Ergebnis UNKLAR: {code}).")
        print("WICHTIG: Bitte zuerst im YouTube Studio prüfen, ob ein Video")
        print("angelegt wurde, BEVOR du es erneut versuchst (Duplikat-Gefahr).")
    else:
        print(f"{_NOT_RUN} (blockiert/fehlgeschlagen: {code}).")
        print(f"  message: {result.get('message')}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
