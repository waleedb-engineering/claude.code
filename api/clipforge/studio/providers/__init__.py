"""Provider-Gateway: Registry, Readiness und automatische Stimmenauswahl."""

from __future__ import annotations

from ..errors import StudioError
from .base import ImageProvider, PlaceholderProvider, Provider, VoiceProvider, VoiceResult
from .local import (
    EspeakVoice, MacSayVoice, MockImage, MockVoice, PiperVoice, SilentVoice, WindowsSapiVoice,
)
from .remote import ElevenLabsVoice, OpenAIImage, OpenAIVoice

# Reihenfolge = Priorität der automatischen Auswahl (lokal vor Cloud).
_VOICES: list[VoiceProvider] = [
    MacSayVoice(), WindowsSapiVoice(), PiperVoice(), EspeakVoice(),
    ElevenLabsVoice(), OpenAIVoice(), MockVoice(), SilentVoice(),
]
_IMAGES: list[ImageProvider] = [OpenAIImage(), MockImage()]
_PLACEHOLDERS: list[Provider] = [
    PlaceholderProvider(
        "ai_video", "video", "KI-Video (Text→Video)",
        "Noch kein Adapter vorhanden. Alternative: KI-Bilder mit Ken-Burns-Animation."),
    PlaceholderProvider(
        "talking_avatar", "avatar", "Talking Avatar",
        "Noch kein Adapter vorhanden. Die Schnittstelle (Provider-Slot) ist vorbereitet."),
    PlaceholderProvider(
        "face_swap", "face_swap", "Face Swap",
        "Nicht verfügbar. Würde ausdrückliche Einwilligung der abgebildeten Person "
        "erfordern; es gibt bewusst keinen Adapter.", "studio_face_swap"),
    PlaceholderProvider(
        "voice_cloning", "voice_clone", "Voice Cloning",
        "Nicht verfügbar. Würde ausdrückliche Zustimmung des Stimminhabers erfordern; "
        "es gibt bewusst keinen Adapter.", "studio_voice_cloning"),
]


def all_providers() -> list[Provider]:
    return [*_VOICES, *_IMAGES, *_PLACEHOLDERS]


def readiness() -> list[dict]:
    return [p.info() for p in all_providers()]


def get_voice(provider_id: str) -> VoiceProvider:
    for p in _VOICES:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Voice-Provider '{provider_id}'.", 400)


def get_image(provider_id: str) -> ImageProvider:
    for p in _IMAGES:
        if p.id == provider_id:
            return p
    raise StudioError("provider_unknown", f"Unbekannter Bild-Provider '{provider_id}'.", 400)


def require_ready(provider: Provider) -> None:
    state, hint = provider.status()
    if state != "ready":
        raise StudioError(
            "provider_not_configured",
            f"Provider '{provider.label}' ist nicht einsatzbereit. {hint}".strip(), 409,
            {"provider": provider.id, "status": state})


def select_voice(language: str, tone: str = "", provider_id: str | None = None,
                 voice_id: str | None = None, allow_paid: bool = False) -> dict:
    """Wählt Provider + Stimme nach Sprache und Ton.

    Ohne Vorgabe ("auto"): erster einsatzbereiter Provider, der die Sprache
    kann — lokale zuerst, kostenpflichtige nur mit `allow_paid`. Fällt immer
    auf `none` (Stille) zurück, damit ein Render nie an der Stimme scheitert.
    """
    lang = language if language else "de"
    candidates: list[VoiceProvider]
    if provider_id and provider_id != "auto":
        candidates = [get_voice(provider_id)]
        require_ready(candidates[0])
    else:
        candidates = [p for p in _VOICES
                      if p.status()[0] == "ready" and (allow_paid or not p.paid)
                      and p.id != "mock"]
    for prov in candidates:
        if lang not in prov.languages and prov.id != "none":
            continue
        voices = prov.voices(lang)
        if not voices:
            continue
        chosen = next((v for v in voices if v["id"] == voice_id), None)
        if chosen is None and tone:
            chosen = next((v for v in voices if v["tone"] == tone), None)
        chosen = chosen or voices[0]
        return {"provider": prov.id, "voice_id": chosen["id"], "label": chosen["label"],
                "tone": chosen["tone"], "language": lang,
                "produces_speech": prov.produces_speech}
    return {"provider": "none", "voice_id": "silent", "label": "Stille", "tone": "neutral",
            "language": lang, "produces_speech": False}


__all__ = [
    "ImageProvider", "Provider", "VoiceProvider", "VoiceResult", "all_providers",
    "get_image", "get_voice", "readiness", "require_ready", "select_voice",
]
