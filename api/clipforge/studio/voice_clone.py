"""Eigene Stimme klonen — nur mit ausdrücklicher, festgehaltener Einwilligung.

Pflicht für jeden Klon:
  - Erklärung, wessen Stimme es ist: die eigene ODER eine fremde mit
    nachweisbarer schriftlicher Erlaubnis (Name der Person wird gespeichert),
  - Bestätigung, dass die Stimme nicht zur Täuschung über die Identität
    eingesetzt wird.
Der Einwilligungsnachweis (Zeitpunkt, Text, Konto, Prüfsummen der Proben)
wird lokal gespeichert. Ohne ihn wird nichts an den Anbieter gesendet.
"""

from __future__ import annotations

import hashlib
import os

from .errors import ProviderError, StudioError
from .storage import new_id, now_iso, read_json, require_id, studio_dir, write_json_atomic

MAX_SAMPLES = 5
MAX_SAMPLE_BYTES = 10 * 1024 * 1024
CONSENT_TEXT = {
    "own": "Ich bestätige, dass dies meine eigene Stimme ist.",
    "permission": ("Ich bestätige, dass mir die genannte Person ihre ausdrückliche, schriftliche "
                   "Erlaubnis gegeben hat, ihre Stimme zu klonen und zu verwenden."),
}
NO_DECEPTION = ("Ich werde die geklonte Stimme nicht verwenden, um über die Identität einer "
                "Person zu täuschen oder Aussagen vorzutäuschen, die sie nicht gemacht hat.")


def _path() -> str:
    path = os.path.join(studio_dir(), "voices")
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "clones.json")


def list_clones() -> list[dict]:
    data = read_json(_path(), [])
    return data if isinstance(data, list) else []


def create_clone(*, name: str, speaker: str, basis: str, no_deception: bool,
                 samples: list[str], user: str | None, provider) -> dict:
    name = " ".join((name or "").split())[:60]
    speaker = " ".join((speaker or "").split())[:80]
    if not name:
        raise StudioError("validation_error", "Bitte einen Namen für die Stimme angeben.")
    if basis not in CONSENT_TEXT:
        raise StudioError("consent_required",
                          "Bitte angeben, ob es die eigene Stimme ist oder eine Erlaubnis vorliegt.")
    if basis == "permission" and len(speaker) < 3:
        raise StudioError("consent_required", "Bitte den Namen der Person angeben, deren Stimme es ist.")
    if not no_deception:
        raise StudioError("consent_required", "Bitte die Erklärung zur Nicht-Täuschung bestätigen.")
    if not samples or len(samples) > MAX_SAMPLES:
        raise StudioError("validation_error", f"Bitte 1 bis {MAX_SAMPLES} Sprachproben hochladen.")
    digests = []
    for path in samples:
        with open(path, "rb") as fh:
            digests.append(hashlib.sha256(fh.read()).hexdigest())
    try:
        voice_id = provider.clone(name, samples, f"ClipForge: {CONSENT_TEXT[basis]}")
    except ProviderError as exc:
        raise StudioError("provider_failed", f"Stimmklon fehlgeschlagen: {exc}", 502) from exc
    record = {
        "id": new_id(), "name": name, "provider": "elevenlabs", "voice_id": voice_id,
        "created_at": now_iso(),
        "consent": {"basis": basis, "speaker": speaker if basis == "permission" else "eigene Stimme",
                    "statement": CONSENT_TEXT[basis], "no_deception": NO_DECEPTION,
                    "confirmed_at": now_iso(), "confirmed_by": user or "lokal",
                    "sample_sha256": digests},
    }
    clones = list_clones()
    clones.append(record)
    write_json_atomic(_path(), clones)
    return record


def delete_clone(clone_id: str, provider) -> None:
    require_id(clone_id, "Stimm-ID")
    clones = list_clones()
    record = next((c for c in clones if c["id"] == clone_id), None)
    if record is None:
        raise StudioError("clone_not_found", "Diese geklonte Stimme gibt es nicht.", 404)
    try:
        provider.delete(record["voice_id"])
    except ProviderError as exc:
        raise StudioError("provider_failed", f"Löschen beim Anbieter fehlgeschlagen: {exc}", 502) from exc
    write_json_atomic(_path(), [c for c in clones if c["id"] != clone_id])
