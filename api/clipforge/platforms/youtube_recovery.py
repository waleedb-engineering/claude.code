"""Startup-Recovery-Scanner + Reconciliation (Phase 3c).

Zweck: nach einem Crash/Neustart verwaiste (stale) YouTube-Upload-Zustände
**sicher** behandeln — OHNE jemals blind neu hochzuladen.

Sicherheits-Invarianten (durch Tests abgesichert):
  - **Kein Blind-Upload.** Der Scanner startet NIE einen Upload.
  - `published` NUR bei **eindeutiger** Remote-Bestätigung über die exakte
    `external_post_id`. KEINE Titel-/Caption-/Dateinamen-Heuristik, KEINE Suche
    nach „ähnlichen" Videos.
  - Unbekannter/nicht eindeutig prüfbarer Remote-Status ⇒ `uncertain` +
    `requires_manual_check` (nie Fake-Erfolg, nie automatischer Retry).
  - `failed` nur, wenn das Nicht-Vorhandensein remote **eindeutig** bewiesen ist
    (Retry dann sicher).
  - Frische (nicht-stale) Uploads werden NICHT angefasst.
  - Enthält NIE Tokens/Secrets/Session-URIs.
"""

from __future__ import annotations

import datetime
import glob
import json
import os

from ..publishing import apply_publish_state, load_draft, publishing_dir
from . import youtube_state as ystate

# Reconciliation-Ergebnis-Codes (persistiert als reconciliation_status).
RECON_CONFIRMED = "confirmed_remote"          # Remote-Video eindeutig vorhanden
RECON_REMOTE_MISSING = "remote_missing"        # Remote eindeutig NICHT vorhanden
RECON_NO_IDENTIFIER = "no_unique_identifier"   # keine external_post_id → nicht prüfbar
RECON_VERIFIER_UNAVAILABLE = "verifier_unavailable"
RECON_VERIFY_ERROR = "verify_error"            # Netzwerk/unklar → uncertain
RECON_CONFIRMED_ON_UPLOAD = "confirmed_on_upload"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ReconciliationService:
    """Prüft NUR den Remote-Status einer bekannten `external_post_id` und
    korrigiert den lokalen Zustand. Startet NIE einen Upload.

    `verifier(video_id)` ist injizierbar und MUSS zurückgeben:
      - `("found", data)`   → Video mit exакt dieser ID existiert (privat).
      - `("not_found", None)` → Video existiert eindeutig NICHT.
      - beliebige Exception  → unbekannt/Netzwerk (→ uncertain, kein Fake).
    Fehlt der Verifier, ist keine eindeutige Bestätigung möglich → uncertain.
    """

    def __init__(self, verifier=None, now_fn=None):
        self._verifier = verifier
        self._now = now_fn or _now

    def reconcile(self, job_dir: str, publishing_id: str, draft: dict) -> dict:
        """Reconciled EINEN Draft. Gibt das (sichere) upload_status-artige
        Ergebnis-Dict der neuen Lage zurück (ohne Secrets)."""
        state = ystate.current_state(draft)
        ext = draft.get("external_post_id")

        # Nur reconciling/uncertain (oder stale-active, das der Scanner bereits
        # nach reconciling verschoben hat) sind sinnvoll reconcilebar.
        if state == ystate.STATE_PUBLISHED:
            return self._result(draft, "already_published")

        if not ext:
            # KEINE eindeutige ID → keine Heuristik erlaubt → uncertain + manuell.
            return self._apply(job_dir, publishing_id, ystate.STATE_UNCERTAIN,
                               RECON_NO_IDENTIFIER, requires_manual_check=True)

        if self._verifier is None:
            return self._apply(job_dir, publishing_id, ystate.STATE_UNCERTAIN,
                               RECON_VERIFIER_UNAVAILABLE, requires_manual_check=True)

        try:
            verdict, data = self._verifier(ext)
        except Exception:  # noqa: BLE001 — Netzwerk/unklar, NIE Fake-Erfolg
            return self._apply(job_dir, publishing_id, ystate.STATE_UNCERTAIN,
                               RECON_VERIFY_ERROR, requires_manual_check=True)

        if verdict == "found" and isinstance(data, dict) and data.get("id") == ext:
            # Eindeutig bestätigt → published.
            return self._apply(job_dir, publishing_id, ystate.STATE_PUBLISHED,
                               RECON_CONFIRMED,
                               extra={"external_post_id": ext,
                                      "published_at": self._now()})
        if verdict == "not_found":
            # Eindeutig NICHT vorhanden → failed (Retry sicher), ID verwerfen.
            return self._apply(job_dir, publishing_id, ystate.STATE_FAILED,
                               RECON_REMOTE_MISSING,
                               extra={"external_post_id": None})
        # Alles andere (uneindeutig) → uncertain.
        return self._apply(job_dir, publishing_id, ystate.STATE_UNCERTAIN,
                           RECON_VERIFY_ERROR, requires_manual_check=True)

    def _apply(self, job_dir, publishing_id, to, recon_status, *,
               requires_manual_check=None, extra=None) -> dict:
        current = load_draft(job_dir, publishing_id) or {}
        frm = ystate.current_state(current)
        # Selbstübergang eines ruhenden Zustands (z. B. uncertain→uncertain):
        # kein State-Wechsel, nur Metadaten (recon_status/Flags) aktualisieren.
        if frm == to and to not in ystate.ACTIVE_STATES:
            meta = {"reconciliation_status": recon_status,
                    "reconciliation_checked_at": self._now(),
                    "last_transition_at": self._now()}
            if requires_manual_check is not None:
                meta["requires_manual_check"] = bool(requires_manual_check)
            if extra:
                meta.update(extra)
            apply_publish_state(job_dir, publishing_id, meta)
            return self._result(load_draft(job_dir, publishing_id) or {}, recon_status)
        # Falls der aktuelle Zustand keinen direkten Übergang erlaubt, erst nach
        # reconciling (falls von dort erlaubt). Sonst best-effort belassen.
        if frm != to and not ystate.can_transition(frm, to):
            if ystate.can_transition(frm, ystate.STATE_RECONCILING):
                inter = ystate.transition(current, ystate.STATE_RECONCILING,
                                          now=self._now(),
                                          reconciliation_status=recon_status)
                apply_publish_state(job_dir, publishing_id, inter)
                current = load_draft(job_dir, publishing_id) or {}
        updates = ystate.transition(
            current, to, now=self._now(),
            reconciliation_status=recon_status,
            requires_manual_check=requires_manual_check,
            error_code=None if to == ystate.STATE_PUBLISHED else current.get("last_error_code"),
            extra=extra)
        apply_publish_state(job_dir, publishing_id, updates)
        return self._result(load_draft(job_dir, publishing_id) or {}, recon_status)

    @staticmethod
    def _result(draft: dict, recon_status: str) -> dict:
        return {
            "state": ystate.current_state(draft),
            "reconciliation_status": draft.get("reconciliation_status") or recon_status,
            "external_post_id_present": bool(draft.get("external_post_id")),
            "requires_manual_check": bool(draft.get("requires_manual_check")),
            "no_secrets": True,
        }


class RecoveryScanner:
    """Scannt beim Start alle YouTube-Drafts, erkennt **stale** aktive Zustände
    und verschiebt sie SICHER. Startet NIE einen Upload."""

    def __init__(self, settings, reconciler: ReconciliationService | None = None,
                 now_fn=None):
        self.settings = settings
        self.reconciler = reconciler
        self._now = now_fn or _now

    def _age(self, iso_ts, now_iso) -> float | None:
        if not isinstance(iso_ts, str) or not iso_ts:
            return None
        try:
            a = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
            b = datetime.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if a.tzinfo is None:
            a = a.replace(tzinfo=datetime.timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=datetime.timezone.utc)
        return (b - a).total_seconds()

    def _is_stale(self, draft: dict, now_iso: str) -> bool:
        if ystate.current_state(draft) not in ystate.ACTIVE_STATES:
            return False
        activity = (draft.get("last_upload_activity_at")
                    or draft.get("last_transition_at")
                    or draft.get("upload_started_at"))
        age = self._age(activity, now_iso)
        if age is None:
            return False
        return age > int(self.settings.youtube_stale_upload_seconds)

    def _iter_youtube_drafts(self, jobs_dir: str):
        for jobdir in sorted(glob.glob(os.path.join(jobs_dir, "*"))):
            pdir = publishing_dir(jobdir)
            if not os.path.isdir(pdir):
                continue
            for path in sorted(glob.glob(os.path.join(pdir, "*.json"))):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        draft = json.load(fh)
                except (OSError, ValueError):
                    continue
                if not isinstance(draft, dict):
                    continue
                if draft.get("platform") != "youtube_shorts":
                    continue
                pid = draft.get("publishing_id")
                if pid:
                    yield jobdir, pid, draft

    def _clear_lock(self, job_dir: str, publishing_id: str) -> None:
        lock = os.path.join(publishing_dir(job_dir), f"{publishing_id}.uploadlock")
        try:
            if os.path.exists(lock):
                os.unlink(lock)
        except OSError:
            pass

    def scan(self, jobs_dir: str) -> dict:
        """Scannt einmalig. Verschiebt stale aktive Zustände:
          - hat `external_post_id` → reconciling (+ optional sofort reconcilen)
          - sonst → uncertain + requires_manual_check
        Frische Drafts bleiben unberührt. Startet NIE einen Upload."""
        summary = {"scanned": 0, "stale": 0, "moved_reconciling": 0,
                   "moved_uncertain": 0, "reconciled_published": 0,
                   "enabled": bool(self.settings.youtube_recovery_scan_enabled),
                   "actions": []}
        if not self.settings.youtube_recovery_scan_enabled:
            return summary
        if not os.path.isdir(jobs_dir):
            return summary
        now_iso = self._now()
        for job_dir, pid, draft in self._iter_youtube_drafts(jobs_dir):
            summary["scanned"] += 1
            if not self._is_stale(draft, now_iso):
                continue  # frisch → NICHT anfassen
            summary["stale"] += 1
            state = ystate.current_state(draft)
            self._clear_lock(job_dir, pid)
            has_id = bool(draft.get("external_post_id"))
            if has_id:
                # Kandidaten-ID vorhanden → reconciling (Fenster E).
                to_recon = ystate.transition(
                    draft, ystate.STATE_RECONCILING, now=self._now(),
                    reconciliation_status="pending",
                    extra={"upload_progress": None})
                apply_publish_state(job_dir, pid, to_recon)
                summary["moved_reconciling"] += 1
                action = {"publishing_id": pid, "from": state, "to": "reconciling"}
                if self.reconciler is not None:
                    res = self.reconciler.reconcile(job_dir, pid,
                                                    load_draft(job_dir, pid) or {})
                    action["reconciled_to"] = res.get("state")
                    if res.get("state") == ystate.STATE_PUBLISHED:
                        summary["reconciled_published"] += 1
                summary["actions"].append(action)
            else:
                # KEINE eindeutige ID → nicht verifizierbar → uncertain + manuell.
                to_unc = ystate.transition(
                    draft, ystate.STATE_UNCERTAIN, now=self._now(),
                    reconciliation_status=RECON_NO_IDENTIFIER,
                    requires_manual_check=True,
                    error_code="upload_result_uncertain",
                    extra={"upload_progress": None})
                apply_publish_state(job_dir, pid, to_unc)
                summary["moved_uncertain"] += 1
                summary["actions"].append(
                    {"publishing_id": pid, "from": state, "to": "uncertain"})
        return summary


def default_remote_verifier(upload_service):
    """Echter, ID-basierter Remote-Verifier über die offizielle Google-Library
    (`videos().list(part="status", id=<external_post_id>)`). NUR exakte
    ID-Prüfung — KEINE Titel-/Namens-Heuristik.

    Rückgabe: `("found", {"id":..,"status":..})` | `("not_found", None)`.
    Import-/Credential-/Netzwerkfehler propagieren als Exception → der
    ReconciliationService wertet das als `uncertain` (nie Fake-Erfolg).

    HINWEIS: In automatischen Tests wird IMMER ein Fake-Verifier injiziert —
    diese Funktion (und damit ein echter Google-Call) läuft dort NIE.
    """
    def _verify(video_id: str):
        from googleapiclient.discovery import build  # type: ignore
        creds, err = upload_service.prepare_credentials()
        if err:
            raise RuntimeError("credentials_unavailable")
        creds, err = upload_service.refresh_credentials_if_needed(creds)
        if err:
            raise RuntimeError("credentials_unavailable")
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = youtube.videos().list(part="status", id=video_id).execute()
        for item in (resp.get("items") or []):
            if item.get("id") == video_id:
                return "found", {"id": video_id, "status": item.get("status")}
        return "not_found", None
    return _verify
