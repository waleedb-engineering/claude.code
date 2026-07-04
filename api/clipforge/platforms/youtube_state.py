"""Persistente, crash-sichere YouTube-Upload-State-Machine (Phase 3c).

Zentrale Definition der Upload-Zustände + **erlaubten** Übergänge. KEINE
verstreuten String-Vergleiche mehr — alle Transitionen laufen über `transition()`,
das validiert, Checkpoint-Felder setzt und eine (gekappte) Transition-History
schreibt.

Enthält NIE Tokens/Secrets/Session-URIs. Alle Funktionen sind rein (kein I/O):
sie bekommen den aktuellen Draft und geben ein `updates`-Dict zurück, das der
Aufrufer atomar über `publishing.apply_publish_state` persistiert.

Crash-Fenster-Modell (welcher Zustand ist wie sicher wiederherstellbar) ist in
docs/YOUTUBE_PUBLISHING.md §7f dokumentiert.
"""

from __future__ import annotations

# ---- Zustände ------------------------------------------------------------

STATE_IDLE = "idle"
STATE_PREPARING = "preparing"
STATE_UPLOADING = "uploading"
STATE_RETRY_WAIT = "retry_wait"
STATE_AUTH_REFRESH = "auth_refresh"
STATE_RECONCILING = "reconciling"
STATE_PUBLISHED = "published"
STATE_FAILED = "failed"
STATE_UNCERTAIN = "uncertain"
STATE_REAUTH_REQUIRED = "reauth_required"

STATES = (
    STATE_IDLE, STATE_PREPARING, STATE_UPLOADING, STATE_RETRY_WAIT,
    STATE_AUTH_REFRESH, STATE_RECONCILING, STATE_PUBLISHED, STATE_FAILED,
    STATE_UNCERTAIN, STATE_REAUTH_REQUIRED,
)

# `published` ist terminal (unverlassbar). `failed`/`uncertain`/`reauth_required`
# sind ruhende, aber NICHT terminale Zustände.
TERMINAL_STATES = frozenset({STATE_PUBLISHED})

# „In-flight" — diese Zustände können verwaisen (stale werden).
ACTIVE_STATES = frozenset({
    STATE_PREPARING, STATE_UPLOADING, STATE_RETRY_WAIT,
    STATE_AUTH_REFRESH, STATE_RECONCILING,
})

# Ruhende Zustände, aus denen ein neuer Versuch/Reconcile starten darf.
RESTING_STATES = frozenset({
    STATE_IDLE, STATE_FAILED, STATE_UNCERTAIN, STATE_REAUTH_REQUIRED,
})

# ---- Erlaubte Übergänge (zentral) ---------------------------------------

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_IDLE: frozenset({STATE_PREPARING}),
    STATE_PREPARING: frozenset({
        STATE_UPLOADING, STATE_FAILED, STATE_UNCERTAIN,
        STATE_REAUTH_REQUIRED, STATE_RECONCILING,
    }),
    STATE_UPLOADING: frozenset({
        STATE_RETRY_WAIT, STATE_AUTH_REFRESH, STATE_RECONCILING,
        STATE_PUBLISHED, STATE_FAILED, STATE_UNCERTAIN, STATE_REAUTH_REQUIRED,
    }),
    STATE_RETRY_WAIT: frozenset({
        STATE_UPLOADING, STATE_FAILED, STATE_UNCERTAIN, STATE_RECONCILING,
        STATE_REAUTH_REQUIRED,
    }),
    STATE_AUTH_REFRESH: frozenset({
        STATE_UPLOADING, STATE_REAUTH_REQUIRED, STATE_FAILED,
        STATE_UNCERTAIN, STATE_RECONCILING,
    }),
    STATE_RECONCILING: frozenset({
        STATE_PUBLISHED, STATE_FAILED, STATE_UNCERTAIN, STATE_REAUTH_REQUIRED,
    }),
    STATE_PUBLISHED: frozenset(),  # terminal — kein Verlassen
    # Retry ist NUR aus failed/reauth_required erlaubt (→ preparing).
    # uncertain darf NICHT direkt neu hochladen — nur reconcilen.
    STATE_FAILED: frozenset({STATE_PREPARING, STATE_RECONCILING}),
    STATE_UNCERTAIN: frozenset({STATE_RECONCILING}),
    STATE_REAUTH_REQUIRED: frozenset({STATE_PREPARING, STATE_RECONCILING}),
}

# Wieviele Transition-History-Einträge maximal behalten werden.
MAX_TRANSITION_HISTORY = 30


class InvalidTransition(Exception):
    """Ein nicht erlaubter State-Übergang wurde versucht."""


# ---- Legacy-Kompatibilität (status / idempotency_state) ------------------

def status_for_state(state: str) -> str:
    """Bildet den Upload-State auf den bestehenden Draft-`status` ab."""
    if state in (STATE_PREPARING, STATE_UPLOADING, STATE_RETRY_WAIT,
                 STATE_AUTH_REFRESH, STATE_RECONCILING):
        return "publishing"
    if state == STATE_PUBLISHED:
        return "published"
    if state in (STATE_FAILED, STATE_UNCERTAIN, STATE_REAUTH_REQUIRED):
        return "failed"
    return "ready"  # idle


def idempotency_for_state(state: str) -> str:
    """Bildet den Upload-State auf das bestehende `idempotency_state` ab
    (damit die vorhandenen Gates unverändert greifen)."""
    if state in (STATE_PREPARING, STATE_UPLOADING, STATE_RETRY_WAIT,
                 STATE_AUTH_REFRESH, STATE_RECONCILING):
        return "in_progress"
    if state == STATE_PUBLISHED:
        return "succeeded"
    if state == STATE_UNCERTAIN:
        return "uncertain"
    if state in (STATE_FAILED, STATE_REAUTH_REQUIRED):
        return "failed"
    return "never_attempted"  # idle


def current_state(draft: dict) -> str:
    """Ermittelt den aktuellen State: explizites `upload_state` gewinnt; sonst
    Rekonstruktion aus Legacy-Feldern (rückwärtskompatibel)."""
    st = draft.get("upload_state")
    if st in STATES:
        return st
    if draft.get("external_post_id") or draft.get("status") == "published":
        return STATE_PUBLISHED
    idem = draft.get("idempotency_state")
    if idem == "uncertain":
        return STATE_UNCERTAIN
    if idem == "in_progress" or draft.get("status") == "publishing":
        return STATE_UPLOADING
    if idem == "failed" or draft.get("status") == "failed":
        return STATE_FAILED
    return STATE_IDLE


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, frozenset())


def _safe_transition_entry(entry: dict) -> dict:
    # Audit-Fix: korrupte (Nicht-Dict-)Einträge dürfen nie crashen.
    if not isinstance(entry, dict):
        return {"from": None, "to": "corrupt_entry", "at": None}
    fields = ("from", "to", "at", "error_category", "error_code")
    out: dict = {}
    for k in fields:
        v = entry.get(k)
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out


def transition(
    draft: dict, to: str, *, now: str,
    error_category: str | None = None,
    error_code: str | None = None,
    retry_count: int | None = None,
    current_attempt: int | None = None,
    requires_reauth: bool | None = None,
    requires_manual_check: bool | None = None,
    reconciliation_status: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Validiert den Übergang und baut das `updates`-Dict (persistiert der
    Aufrufer atomar). Wirft `InvalidTransition` bei unerlaubtem Übergang.

    Setzt zusätzlich die Legacy-Felder `status`/`idempotency_state` sowie die
    Checkpoint-Felder und hängt einen Transition-History-Eintrag an (gekappt).
    Enthält NIE Tokens/Secrets.
    """
    if to not in STATES:
        raise InvalidTransition(f"Unbekannter Zielzustand: {to!r}")
    frm = current_state(draft)
    if frm == to:
        # Idempotenter „touch" nur für aktive Zustände (Heartbeat) erlaubt.
        if to not in ACTIVE_STATES:
            raise InvalidTransition(f"Kein Selbstübergang aus {frm!r}")
    elif not can_transition(frm, to):
        raise InvalidTransition(f"Unerlaubter Übergang {frm!r} → {to!r}")

    raw_hist = draft.get("state_transition_history")
    history = [e for e in raw_hist if isinstance(e, dict)] if isinstance(raw_hist, list) else []
    history.append(_safe_transition_entry({
        "from": frm, "to": to, "at": now,
        "error_category": error_category, "error_code": error_code,
    }))
    history = history[-MAX_TRANSITION_HISTORY:]

    updates: dict = {
        "upload_state": to,
        "status": status_for_state(to),
        "idempotency_state": idempotency_for_state(to),
        "last_transition_at": now,
        "state_transition_history": history,
    }
    # Aktivitäts-/Startzeitpunkte.
    if to in ACTIVE_STATES:
        updates["last_upload_activity_at"] = now
        if frm not in ACTIVE_STATES:  # neuer In-flight-Abschnitt beginnt
            updates["upload_started_at"] = now
    # Fehler-Checkpoints (immer setzen, damit „alte" Fehler nicht kleben).
    updates["last_error_category"] = error_category
    updates["last_error_code"] = error_code
    if error_code is not None:
        updates["last_publish_error"] = error_code  # Legacy-Feld konsistent
        updates["error"] = error_code
    elif to in (STATE_PUBLISHED,):
        updates["last_publish_error"] = None
        updates["error"] = None
    # Flags (default aus Zielzustand ableiten, überschreibbar).
    updates["requires_reauth"] = (
        requires_reauth if requires_reauth is not None
        else (to == STATE_REAUTH_REQUIRED))
    updates["requires_manual_check"] = (
        requires_manual_check if requires_manual_check is not None
        else (to == STATE_UNCERTAIN))
    if retry_count is not None:
        updates["retry_count"] = int(retry_count)
    if current_attempt is not None:
        updates["current_attempt"] = int(current_attempt)
    if reconciliation_status is not None:
        updates["reconciliation_status"] = reconciliation_status
        updates["reconciliation_checked_at"] = now
    if extra:
        updates.update(extra)
    return updates


def transition_history_summary(draft: dict, limit: int = MAX_TRANSITION_HISTORY) -> list[dict]:
    hist = draft.get("state_transition_history")
    if not isinstance(hist, list):
        hist = []
    return [_safe_transition_entry(e) for e in hist[-limit:]]
