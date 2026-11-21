"""Zentrale Anbieter-Übersicht: Status, Kosten, Limits, Fallback, Verifizierung.

Kosten/Limits sind Richtwerte (Stand der Recherche) — maßgeblich ist der
Anbieter. „live_verified“ = gegen den echten Dienst geprüft (sonst nur gegen
nachgebildete Antworten oder lokal)."""

from __future__ import annotations

META = {
    # id: (Kategorie, Kosten, Limits, Fallback)
    "espeak": ("Stimme lokal", "0", "–", "–"),
    "piper": ("Stimme lokal", "0", "–", "eSpeak / Systemstimme"),
    "macos_say": ("Stimme lokal", "0", "nur macOS", "eSpeak"),
    "windows_sapi": ("Stimme lokal", "0", "nur Windows", "eSpeak"),
    "elevenlabs": ("Stimme Cloud", "ca. 0,15–0,30 USD/1000 Zeichen", "Tarif-Kontingent", "Piper/eSpeak"),
    "openai_tts": ("Stimme Cloud", "ca. 0,015 USD/1000 Zeichen", "Rate-Limits je Konto", "Piper/eSpeak"),
    "elevenlabs_clone": ("Stimmklon", "bezahlter ElevenLabs-Tarif", "Anzahl Stimmen je Tarif", "–"),
    "openai_image": ("KI-Bild", "ca. 0,04–0,08 USD/Bild", "Rate-Limits", "Motion-Hintergrund"),
    "fal_video": ("KI-Video", "ca. 0,05–0,30 USD/s", "Warteschlange", "KI-Bild → Motion"),
    "fal_avatar": ("Talking Avatar", "ca. 0,02–0,10 USD/s", "Warteschlange", "Avatar-Standbild"),
    "face_swap": ("Face Swap", "ca. 0,05 USD/Bild", "Warteschlange", "–"),
    "none": ("Stimme", "0", "–", "–"),
}
KEYS = {
    "anthropic": ("LLM (Skripte, Agent, Übersetzung)", "Cent-Bereich je Aufruf", "Rate-Limits je Konto",
                  "Regeln / Ollama"),
    "openai": ("LLM, TTS, Bilder", "nach Nutzung", "Rate-Limits je Konto", "lokal"),
    "pexels": ("Stock-Medien", "0 (kostenloser Schlüssel)", "ca. 200 Anfragen/h", "eigene Mediathek"),
    "pixabay": ("Stock-Medien", "0 (kostenloser Schlüssel)", "ca. 100 Anfragen/min", "eigene Mediathek"),
    "youtube_data": ("Trends", "0 (Kontingent)", "10 000 Einheiten/Tag Standard", "manuelle Ideen"),
    "gemini": ("LLM (KI-Assistent, nur mit Bestätigung)", "Gratis-Kontingent möglich", "je Modell", "–"),
    "huggingface": ("Modell-Downloads (noch ungenutzt)", "0", "–", "–"),
    "elevenlabs": ("Stimme/Stimmklon", "Tarif", "Kontingent", "Piper"),
}


def matrix() -> list[dict]:
    from ..agent import planner
    from . import credentials
    from .providers import readiness
    from .translate import engines_status
    rows = []
    for r in readiness():
        if r["id"] in ("mock", "mock_image"):
            continue
        cat, cost, limits, fb = META.get(r["id"], (r["kind"], "?", "?", "–"))
        rows.append({"id": r["id"], "label": r["label"], "category": cat, "status": r["status"],
                     "paid": bool(r.get("paid")), "cost": cost, "limits": limits,
                     "live_verified": bool(r.get("live_verified")), "fallback": fb})
    for c in credentials.status():
        cat, cost, limits, fb = KEYS.get(c["provider"], ("API", "?", "?", "–"))
        rows.append({"id": f"key:{c['provider']}", "label": c["label"], "category": cat,
                     "status": "ready" if c["configured"] else "not_configured",
                     "paid": c["provider"] in ("anthropic", "openai", "elevenlabs", "gemini"),
                     "cost": cost, "limits": limits, "live_verified": False, "fallback": fb})
    for e in planner.engines():
        rows.append({"id": f"agent:{e['id']}", "label": e["label"], "category": "KI-Assistent",
                     "status": "ready" if e["ready"] else "not_configured", "paid": e["paid"],
                     "cost": f"{e.get('cost_per_message_usd', 0)} USD/Nachricht" if e["paid"] else "0",
                     "limits": "–", "live_verified": e["live_verified"], "fallback": "Regelbasiert"})
    for e in engines_status():
        ready = e["ready"] if isinstance(e["ready"], bool) else any(e["ready"].values())
        rows.append({"id": f"translate:{e['id']}", "label": e["label"], "category": "Übersetzung",
                     "status": "ready" if ready else "not_configured", "paid": e["paid"],
                     "cost": "nach Nutzung" if e["paid"] else "0", "limits": "–",
                     "live_verified": e["live_verified"], "fallback": "manuell"})
    return rows
